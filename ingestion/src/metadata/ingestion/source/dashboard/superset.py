#  Copyright 2021 Collate
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""
Superset source module
"""

import json
import traceback
from typing import Iterable, List, Optional

import dateutil.parser as dateparser

from metadata.generated.schema.api.lineage.addLineage import AddLineageRequest
from metadata.generated.schema.entity.data.dashboard import (
    Dashboard as Lineage_Dashboard,
)
from metadata.generated.schema.entity.data.table import Table
from metadata.generated.schema.entity.services.connections.dashboard.supersetConnection import (
    SupersetConnection,
)
from metadata.generated.schema.entity.services.connections.metadata.openMetadataConnection import (
    OpenMetadataConnection,
)
from metadata.generated.schema.entity.services.dashboardService import (
    DashboardService,
    DashboardServiceType,
)
from metadata.generated.schema.metadataIngestion.workflow import (
    Source as WorkflowSource,
)
from metadata.generated.schema.type.entityLineage import EntitiesEdge
from metadata.generated.schema.type.entityReference import EntityReference
from metadata.ingestion.api.common import Entity
from metadata.ingestion.api.source import InvalidSourceException, SourceStatus
from metadata.ingestion.models.table_metadata import Chart, Dashboard, DashboardOwner
from metadata.ingestion.source.dashboard.dashboard_source import DashboardSourceService
from metadata.utils.fqn import FQN_SEPARATOR
from metadata.utils.logger import ingestion_logger

logger = ingestion_logger()


def get_metric_name(metric):
    """
    Get metric name

    Args:
        metric:
    Returns:
    """
    if not metric:
        return ""
    if isinstance(metric, str):
        return metric
    label = metric.get("label")

    return label or None


def get_filter_name(filter_obj):
    """
    Get filter name

    Args:
        filter_obj:

    Returns:
        str
    """
    sql_expression = filter_obj.get("sqlExpression")
    if sql_expression:
        return sql_expression

    clause = filter_obj.get("clause")
    column = filter_obj.get("subject")
    operator = filter_obj.get("operator")
    comparator = filter_obj.get("comparator")
    return f"{clause} {column} {operator} {comparator}"


def get_owners(owners_obj):
    """
    Get owner

    Args:
        owners_obj:
    Returns:
        list
    """
    owners = []
    for owner in owners_obj:
        dashboard_owner = DashboardOwner(
            first_name=owner["first_name"],
            last_name=owner["last_name"],
            username=owner["username"],
        )
        owners.append(dashboard_owner)
    return owners


# pylint: disable=too-many-return-statements, too-many-branches
def get_service_type_from_database_uri(uri: str) -> str:
    """
    Get service type from database URI

    Args:
        uri (str):

    Returns:
        str
    """
    if uri.startswith("bigquery"):
        return "bigquery"
    if uri.startswith("druid"):
        return "druid"
    if uri.startswith("mssql"):
        return "mssql"
    if uri.startswith("jdbc:postgres:") and uri.index("redshift.amazonaws") > 0:
        return "redshift"
    if uri.startswith("snowflake"):
        return "snowflake"
    if uri.startswith("presto"):
        return "presto"
    if uri.startswith("trino"):
        return "trino"
    if uri.startswith("postgresql"):
        return "postgres"
    if uri.startswith("pinot"):
        return "pinot"
    if uri.startswith("oracle"):
        return "oracle"
    if uri.startswith("mysql"):
        return "mysql"
    if uri.startswith("mongodb"):
        return "mongodb"
    if uri.startswith("hive"):
        return "hive"
    return "external"


class SupersetSource(DashboardSourceService):
    """
    Superset source class

    Args:
        config:
        metadata_config:

    Attributes:
        config:
        metadata_config:
        status:
        platform:
        service_type:
        service:

    """

    config: WorkflowSource
    metadata_config: OpenMetadataConnection
    status: SourceStatus
    platform = "superset"
    service_type = DashboardServiceType.Superset.value

    def __init__(
        self,
        config: WorkflowSource,
        metadata_config: OpenMetadataConnection,
    ):
        super().__init__(config, metadata_config)

    @classmethod
    def create(cls, config_dict: dict, metadata_config: OpenMetadataConnection):
        config = WorkflowSource.parse_obj(config_dict)
        connection: SupersetConnection = config.serviceConnection.__root__.config
        if not isinstance(connection, SupersetConnection):
            raise InvalidSourceException(
                f"Expected SupersetConnection, but got {connection}"
            )
        return cls(config, metadata_config)

    def get_dashboards_list(self) -> Optional[List[object]]:
        """
        Get List of all dashboards
        """
        current_page = 0
        page_size = 25
        total_dashboards = self.client.fetch_total_dashboards()
        while current_page * page_size <= total_dashboards:
            dashboards = self.client.fetch_dashboards(current_page, page_size)
            current_page += 1
            for dashboard in dashboards["result"]:
                yield dashboard

    def get_dashboard_name(self, dashboard_details: dict) -> str:
        """
        Get Dashboard Name
        """
        return dashboard_details["id"]

    def get_dashboard_details(self, dashboard: dict) -> dict:
        """
        Get Dashboard Details
        """
        return dashboard

    def get_dashboard_entity(self, dashboard_details: dict) -> Dashboard:
        """
        Method to Get Dashboard Entity
        """
        self.fetch_dashboard_charts(dashboard_details)
        last_modified = (
            dateparser.parse(dashboard_details.get("changed_on_utc", "now")).timestamp()
            * 1000
        )
        yield Dashboard(
            name=dashboard_details["id"],
            displayName=dashboard_details["dashboard_title"],
            description="",
            url=dashboard_details["url"],
            owners=get_owners(dashboard_details["owners"]),
            charts=self.charts,
            service=EntityReference(id=self.service.id, type="dashboardService"),
            lastModified=last_modified,
        )

    def get_lineage(self, dashboard_details: dict) -> Optional[AddLineageRequest]:
        """
        Get lineage between dashboard and data sources
        """
        logger.info("Lineage not implemented for superset")
        return None

    def fetch_dashboard_charts(self, dashboard_details: dict) -> None:
        """
        Metod to fetch charts linked to dashboard
        """
        raw_position_data = dashboard_details.get("position_json", "{}")
        self.charts = []
        if raw_position_data is not None:
            position_data = json.loads(raw_position_data)
            for key, value in position_data.items():
                if not key.startswith("CHART-"):
                    continue
                chart_id = value.get("meta", {}).get("chartId", "unknown")
                self.charts.append(chart_id)

    def _get_service_type_from_database_id(self, database_id):
        database_json = self.client.fetch_database(database_id)
        sqlalchemy_uri = database_json.get("result", {}).get("sqlalchemy_uri")
        return get_service_type_from_database_uri(sqlalchemy_uri)

    def _get_datasource_from_id(self, datasource_id):
        datasource_json = self.client.fetch_datasource(datasource_id)
        schema_name = datasource_json.get("result", {}).get("schema")
        table_name = datasource_json.get("result", {}).get("table_name")
        database_id = datasource_json.get("result", {}).get("database", {}).get("id")
        database_name = (
            datasource_json.get("result", {}).get("database", {}).get("database_name")
        )

        if database_id and table_name:
            platform = self._get_service_type_from_database_id(database_id)
            dataset_fqn = (
                f"{platform}{FQN_SEPARATOR}{database_name + FQN_SEPARATOR if database_name else ''}"
                f"{schema_name + FQN_SEPARATOR if schema_name else ''}"
                f"{table_name}"
            )
            return dataset_fqn
        return None

    def _check_lineage(self, chart_id, datasource_text):
        if datasource_text and hasattr(self.service_connection, "dbServiceName"):
            chart_data = self.client.fetch_charts_with_id(chart_id)
            dashboards = chart_data["result"].get("dashboards")
            for dashboard in dashboards:
                try:
                    from_entity = self.metadata.get_by_name(
                        entity=Table,
                        fqn=f"{self.service_connection.dbServiceName}.{datasource_text}",
                    )
                    to_entity = self.metadata.get_by_name(
                        entity=Lineage_Dashboard,
                        fqn=f"{self.config.serviceName}.{dashboard['id']}",
                    )
                    if from_entity and to_entity:
                        lineage = AddLineageRequest(
                            edge=EntitiesEdge(
                                fromEntity=EntityReference(
                                    id=from_entity.id.__root__, type="table"
                                ),
                                toEntity=EntityReference(
                                    id=to_entity.id.__root__, type="dashboard"
                                ),
                            )
                        )
                        yield lineage

                except Exception as err:
                    logger.debug(traceback.format_exc())
                    logger.error(err)

    # pylint: disable=too-many-locals
    def _build_chart(self, chart_json: dict) -> Chart:
        chart_id = chart_json["id"]
        last_modified = (
            dateparser.parse(chart_json.get("changed_on_utc", "now")).timestamp() * 1000
        )
        params = json.loads(chart_json["params"])
        metrics = [
            get_metric_name(metric)
            for metric in (params.get("metrics", []) or [params.get("metric")])
        ]
        filters = [
            get_filter_name(filter_obj)
            for filter_obj in params.get("adhoc_filters", [])
        ]
        group_bys = params.get("groupby", []) or []
        if isinstance(group_bys, str):
            group_bys = [group_bys]
        custom_properties = {
            "Metrics": ", ".join(metrics),
            "Filters": ", ".join(filters),
            "Dimensions": ", ".join(group_bys),
        }

        chart = Chart(
            name=chart_id,
            displayName=chart_json["slice_name"],
            description="",
            chart_type=chart_json["viz_type"],
            url=chart_json["url"],
            owners=get_owners(chart_json["owners"]),
            datasource_fqn=self._get_datasource_from_id(chart_json["datasource_id"]),
            lastModified=last_modified,
            service=EntityReference(id=self.service.id, type="dashboardService"),
            custom_props=custom_properties,
        )
        yield from self._check_lineage(chart_id, chart_json.get("datasource_name_text"))
        yield chart

    def process_charts(self) -> Optional[Iterable[Chart]]:
        current_page = 0
        page_size = 25
        total_charts = self.client.fetch_total_charts()
        while current_page * page_size <= total_charts:
            charts = self.client.fetch_charts(current_page, page_size)
            current_page += 1
            for chart_json in charts["result"]:
                try:
                    yield from self._build_chart(chart_json)
                except Exception as err:
                    logger.debug(traceback.format_exc())
                    logger.error(err)

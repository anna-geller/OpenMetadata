/*
 *  Copyright 2021 Collate
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at
 *  http://www.apache.org/licenses/LICENSE-2.0
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 */

package org.openmetadata.catalog;

import static org.openmetadata.common.utils.CommonUtil.listOrEmpty;

import com.networknt.schema.JsonSchema;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import lombok.extern.slf4j.Slf4j;
import org.openmetadata.catalog.entity.Type;
import org.openmetadata.catalog.entity.type.CustomProperty;
import org.openmetadata.catalog.util.FullyQualifiedName;
import org.openmetadata.catalog.util.JsonUtils;

/** Type registry used for storing Types in OpenMetadata and customProperties of entity types. */
@Slf4j
public class TypeRegistry {
  /** Type map used for storing both Property Types and Entity Types */
  protected static final Map<String, Type> TYPES = new ConcurrentHashMap<>();

  /** Custom property map (fully qualified customPropertyName) to (customProperty) */
  protected static final Map<String, CustomProperty> CUSTOM_PROPERTIES = new ConcurrentHashMap<>();

  /** Custom property map (fully qualified customPropertyName) to (jsonSchema) */
  protected static final Map<String, JsonSchema> CUSTOM_PROPERTY_SCHEMAS = new ConcurrentHashMap<>();

  private static final TypeRegistry INSTANCE = new TypeRegistry();

  private TypeRegistry() {
    /* Singleton instance */
  }

  public static TypeRegistry instance() {
    return INSTANCE;
  }

  public void addType(Type type) {
    TYPES.put(type.getName(), type);
    LOG.info("Updated type {}\n", type.getName());

    // Store custom properties added to a type
    for (CustomProperty property : type.getCustomProperties()) {
      TypeRegistry.instance().addCustomProperty(type.getName(), property.getName(), property);
    }
  }

  public void removeType(String typeName) {
    TYPES.remove(typeName);
    LOG.info("Deleted type {}\n", typeName);
    // TODO cleanup custom properties
  }

  private void addCustomProperty(String entityType, String propertyName, CustomProperty customProperty) {
    String customPropertyFQN = getCustomPropertyFQN(entityType, propertyName);
    CUSTOM_PROPERTIES.put(customPropertyFQN, customProperty);
    LOG.info("Adding custom property {}\n", customPropertyFQN);

    JsonSchema jsonSchema = JsonUtils.getJsonSchema(TYPES.get(customProperty.getPropertyType().getName()).getSchema());
    CUSTOM_PROPERTY_SCHEMAS.put(customPropertyFQN, jsonSchema);
    LOG.info("Adding json schema for {} {}\n", customProperty, jsonSchema);
  }

  public JsonSchema getSchema(String entityType, String propertyName) {
    String customPropertyFQN = getCustomPropertyFQN(entityType, propertyName);
    return CUSTOM_PROPERTY_SCHEMAS.get(customPropertyFQN);
  }

  public void validateCustomProperties(Type type) {
    // Validate custom properties added to a type
    for (CustomProperty property : listOrEmpty(type.getCustomProperties())) {
      if (TYPES.get(property.getPropertyType().getName()) == null) {
        throw new IllegalArgumentException(
            String.format(
                "Type %s not found for custom property %s", property.getPropertyType().getName(), property.getName()));
      }
    }
  }

  public static String getCustomPropertyFQNPrefix(String entityType) {
    return FullyQualifiedName.build(entityType, "customProperties");
  }

  public static String getCustomPropertyFQN(String entityType, String propertyName) {
    return FullyQualifiedName.build(entityType, "customProperties", propertyName);
  }

  public static String getPropertyName(String propertyFQN) {
    return FullyQualifiedName.split(propertyFQN)[2];
  }
}

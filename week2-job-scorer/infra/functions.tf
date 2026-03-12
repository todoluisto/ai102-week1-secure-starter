# ─── Storage Account (Blob config + Function runtime) ──────────────
resource "azurerm_storage_account" "functions" {
  name                     = local.storage_account_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  tags = local.common_tags
}

# ─── Blob Container for Function Config ────────────────────────────
resource "azurerm_storage_container" "function_config" {
  name                  = "function-config"
  storage_account_id    = azurerm_storage_account.functions.id
  container_access_type = "private"
}

# ─── Cosmos DB Account (Serverless, SQL API) ───────────────────────
resource "azurerm_cosmosdb_account" "main" {
  name                = local.cosmos_account_name
  resource_group_name = azurerm_resource_group.main.name
  location            = "westus2"
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = "westus2"
    failover_priority = 0
    zone_redundant    = false
  }

  tags = local.common_tags
}

# ─── Cosmos DB Database ────────────────────────────────────────────
resource "azurerm_cosmosdb_sql_database" "jobscorer" {
  name                = "jobscorer"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
}

# ─── Cosmos DB Container ──────────────────────────────────────────
resource "azurerm_cosmosdb_sql_container" "results" {
  name                = "results"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.jobscorer.name
  partition_key_paths = ["/company"]

  indexing_policy {
    indexing_mode = "consistent"

    included_path {
      path = "/*"
    }

    excluded_path {
      path = "/\"_etag\"/?"
    }
  }
}

# ─── App Service Plan (Consumption Y1, Linux) ─────────────────────
resource "azurerm_service_plan" "functions" {
  name                = local.app_service_plan_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1"

  tags = local.common_tags
}

# ─── Function App (Python 3.11) ───────────────────────────────────
resource "azurerm_linux_function_app" "main" {
  name                       = local.function_app_name
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.functions.id
  storage_account_name       = azurerm_storage_account.functions.name
  storage_account_access_key = azurerm_storage_account.functions.primary_access_key

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    "AZURE_KEY_VAULT_URI"         = azurerm_key_vault.main.vault_uri
    "COSMOS_ENDPOINT"             = azurerm_cosmosdb_account.main.endpoint
    "COSMOS_DATABASE"             = "jobscorer"
    "COSMOS_CONTAINER"            = "results"
    "CONFIG_STORAGE_ACCOUNT_NAME" = azurerm_storage_account.functions.name
    "CONFIG_CONTAINER_NAME"       = "function-config"
  }

  tags = local.common_tags
}

# ─── RBAC: Function → Key Vault Secrets User ──────────────────────
resource "azurerm_role_assignment" "func_kv_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_function_app.main.identity[0].principal_id
}

# ─── RBAC: Function → Storage Blob Data Reader ────────────────────
resource "azurerm_role_assignment" "func_storage_blob_reader" {
  scope                = azurerm_storage_account.functions.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_linux_function_app.main.identity[0].principal_id
}

# ─── RBAC: Function → Cosmos DB Built-in Data Contributor ─────────
resource "azurerm_cosmosdb_sql_role_assignment" "func_cosmos_contributor" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  # Built-in "Cosmos DB Built-in Data Contributor" role definition ID
  role_definition_id = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id       = azurerm_linux_function_app.main.identity[0].principal_id
  scope              = azurerm_cosmosdb_account.main.id
}

# ─── RBAC: Current User → Cosmos DB Built-in Data Contributor ─────
resource "azurerm_cosmosdb_sql_role_assignment" "user_cosmos_contributor" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  role_definition_id  = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = data.azurerm_client_config.current.object_id
  scope               = azurerm_cosmosdb_account.main.id
}

# ─── Diagnostics: Function App → Log Analytics ────────────────────
resource "azurerm_monitor_diagnostic_setting" "function_app" {
  name                       = "${local.function_app_name}-diagnostics"
  target_resource_id         = azurerm_linux_function_app.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log { category = "FunctionAppLogs" }
  metric { category = "AllMetrics" }
}

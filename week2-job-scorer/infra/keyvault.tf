# ─── Key Vault ────────────────────────────────────────────────────
resource "azurerm_key_vault" "main" {
  name                       = local.key_vault_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7

  tags = local.common_tags
}

# ─── RBAC: Grant current user Key Vault Secrets Officer ──────────
resource "azurerm_role_assignment" "kv_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# ─── Primary OpenAI Secrets ──────────────────────────────────────
resource "azurerm_key_vault_secret" "openai_key" {
  name         = "openai-key"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.common_tags

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "openai_endpoint" {
  name         = "openai-endpoint"
  value        = azurerm_cognitive_account.openai.endpoint
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.common_tags

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

# ─── Fallback OpenAI Secrets ────────────────────────────────────
resource "azurerm_key_vault_secret" "openai_fallback_key" {
  name         = "openai-fallback-key"
  value        = azurerm_cognitive_account.openai_fallback.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.common_tags

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "openai_fallback_endpoint" {
  name         = "openai-fallback-endpoint"
  value        = azurerm_cognitive_account.openai_fallback.endpoint
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.common_tags

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

# ─── Document Intelligence Secrets ──────────────────────────────
resource "azurerm_key_vault_secret" "doc_intel_key" {
  name         = "doc-intel-key"
  value        = azurerm_cognitive_account.doc_intel.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.common_tags

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

resource "azurerm_key_vault_secret" "doc_intel_endpoint" {
  name         = "doc-intel-endpoint"
  value        = azurerm_cognitive_account.doc_intel.endpoint
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.common_tags

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

# ─── Cosmos DB Endpoint Secret ───────────────────────────────────
resource "azurerm_key_vault_secret" "cosmos_endpoint" {
  name         = "cosmos-endpoint"
  value        = azurerm_cosmosdb_account.main.endpoint
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.common_tags

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

# ─── Storage Connection String Secret ─────────────────────────────
resource "azurerm_key_vault_secret" "storage_connection_string" {
  name         = "storage-connection-string"
  value        = azurerm_storage_account.functions.primary_connection_string
  key_vault_id = azurerm_key_vault.main.id
  content_type = "text/plain"
  tags         = local.common_tags

  depends_on = [azurerm_role_assignment.kv_secrets_officer]
}

# ─── Log Analytics Workspace ─────────────────────────────────────
resource "azurerm_log_analytics_workspace" "main" {
  name                = local.log_analytics_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = local.common_tags
}

# ─── Diagnostics: Primary OpenAI → Log Analytics ────────────────
resource "azurerm_monitor_diagnostic_setting" "openai" {
  name                       = "${local.openai_name}-diagnostics"
  target_resource_id         = azurerm_cognitive_account.openai.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log { category = "Audit" }
  enabled_log { category = "RequestResponse" }
  enabled_log { category = "Trace" }
  metric { category = "AllMetrics" }
}

# ─── Diagnostics: Fallback OpenAI → Log Analytics ───────────────
resource "azurerm_monitor_diagnostic_setting" "openai_fallback" {
  name                       = "${local.openai_fallback_name}-diagnostics"
  target_resource_id         = azurerm_cognitive_account.openai_fallback.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log { category = "Audit" }
  enabled_log { category = "RequestResponse" }
  enabled_log { category = "Trace" }
  metric { category = "AllMetrics" }
}

# ─── Diagnostics: Document Intelligence → Log Analytics ─────────
resource "azurerm_monitor_diagnostic_setting" "doc_intel" {
  name                       = "${local.doc_intel_name}-diagnostics"
  target_resource_id         = azurerm_cognitive_account.doc_intel.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log { category = "Audit" }
  enabled_log { category = "RequestResponse" }
  enabled_log { category = "Trace" }
  metric { category = "AllMetrics" }
}

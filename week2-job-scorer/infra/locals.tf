data "azurerm_client_config" "current" {}

locals {
  # Naming convention: ai102-<svc>-<region>
  resource_group_name = "${var.project}-rsg-${var.region_short}"

  # Primary resources (East US)
  openai_name    = "${var.project}-oai-${var.region_short}"
  doc_intel_name = "${var.project}-fri-${var.region_short}"
  key_vault_name = "${var.project}-kvt2-${var.region_short}"
  log_analytics_name = "${var.project}-law2-${var.region_short}"

  # Fallback resources (North Central US)
  openai_fallback_name = "${var.project}-oai-${var.fallback_region_short}"

  common_tags = {
    project = var.project
    week    = "2"
  }
}

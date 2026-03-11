# ─── Resource Group (import existing from Week 1) ──────────────────
resource "azurerm_resource_group" "main" {
  name     = local.resource_group_name
  location = var.location

  tags = {
    project = var.project
  }

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [tags]
  }
}

# ─── Azure OpenAI — Primary (East US) ─────────────────────────────
resource "azurerm_cognitive_account" "openai" {
  name                  = local.openai_name
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = local.openai_name
  local_auth_enabled    = true

  tags = local.common_tags
}

resource "azurerm_cognitive_deployment" "gpt" {
  name                 = "gpt-4o-mini"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.openai_model_name
    version = var.openai_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }
}

# ─── Azure OpenAI — Fallback (North Central US) ───────────────────
resource "azurerm_cognitive_account" "openai_fallback" {
  name                  = local.openai_fallback_name
  location              = var.fallback_location
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = local.openai_fallback_name
  local_auth_enabled    = true

  tags = local.common_tags
}

resource "azurerm_cognitive_deployment" "gpt_fallback" {
  name                 = "gpt-4o-mini"
  cognitive_account_id = azurerm_cognitive_account.openai_fallback.id

  model {
    format  = "OpenAI"
    name    = var.openai_model_name
    version = var.openai_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = 10
  }
}

# ─── Document Intelligence (Form Recognizer) ──────────────────────
resource "azurerm_cognitive_account" "doc_intel" {
  name                  = local.doc_intel_name
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "FormRecognizer"
  sku_name              = "S0"
  custom_subdomain_name = local.doc_intel_name
  local_auth_enabled    = true

  tags = local.common_tags
}

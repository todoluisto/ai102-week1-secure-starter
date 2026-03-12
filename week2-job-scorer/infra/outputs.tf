output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "openai_endpoint" {
  description = "Primary Azure OpenAI endpoint URL"
  value       = azurerm_cognitive_account.openai.endpoint
}

output "openai_deployment_name" {
  description = "Primary Azure OpenAI model deployment name"
  value       = azurerm_cognitive_deployment.gpt.name
}

output "openai_fallback_endpoint" {
  description = "Fallback Azure OpenAI endpoint URL (North Central US)"
  value       = azurerm_cognitive_account.openai_fallback.endpoint
}

output "openai_fallback_deployment_name" {
  description = "Fallback Azure OpenAI model deployment name"
  value       = azurerm_cognitive_deployment.gpt_fallback.name
}

output "doc_intel_endpoint" {
  description = "Document Intelligence endpoint URL"
  value       = azurerm_cognitive_account.doc_intel.endpoint
}

output "key_vault_uri" {
  description = "Key Vault URI for secret retrieval"
  value       = azurerm_key_vault.main.vault_uri
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID for queries"
  value       = azurerm_log_analytics_workspace.main.workspace_id
}

output "cosmos_endpoint" {
  description = "Cosmos DB account endpoint"
  value       = azurerm_cosmosdb_account.main.endpoint
}

output "storage_account_name" {
  description = "Storage account name for Function App config"
  value       = azurerm_storage_account.functions.name
}

output "function_app_hostname" {
  description = "Function App default hostname"
  value       = azurerm_linux_function_app.main.default_hostname
}

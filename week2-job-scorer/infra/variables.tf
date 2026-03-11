variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
  sensitive   = true
}

variable "location" {
  description = "Primary Azure region"
  type        = string
  default     = "eastus"
}

variable "fallback_location" {
  description = "Fallback Azure region for OpenAI redundancy"
  type        = string
  default     = "northcentralus"
}

variable "project" {
  description = "Project prefix used in resource naming"
  type        = string
  default     = "ai102"
}

variable "region_short" {
  description = "Short region code for primary region"
  type        = string
  default     = "eus"
}

variable "fallback_region_short" {
  description = "Short region code for fallback region"
  type        = string
  default     = "ncus"
}

variable "openai_model_name" {
  description = "Azure OpenAI model to deploy"
  type        = string
  default     = "gpt-4o-mini"
}

variable "openai_model_version" {
  description = "Model version for deployment"
  type        = string
  default     = "2024-07-18"
}

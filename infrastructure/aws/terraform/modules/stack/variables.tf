variable "project" {
  type    = string
  default = "nexaro"
}

variable "environment" {
  type = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment debe ser dev, staging o prod."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "enable_nat" {
  type    = bool
  default = false
}

variable "enable_database" {
  type    = bool
  default = false
}

variable "database_min_acu" {
  type    = number
  default = 0.5
}

variable "database_max_acu" {
  type    = number
  default = 2
}

variable "database_backup_days" {
  type    = number
  default = 7
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "enable_guardduty" {
  type    = bool
  default = false
}

variable "enable_cloudtrail" {
  type    = bool
  default = false
}

variable "force_destroy_buckets" {
  type    = bool
  default = false
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "monthly_budget_usd" {
  type = number
}

variable "alert_email" {
  type = string
}

variable "certificate_arn" {
  type = string
}

variable "image_tag" {
  type        = string
  description = "Etiqueta inmutable de la imagen en ECR (no 'latest')."
}

variable "desired_count" {
  type    = number
  default = 0
}

variable "allowed_origins" {
  type        = list(string)
  description = "Orígenes https de la aplicación (ALLOWED_ORIGINS)."
}

variable "bedrock_model_arns" {
  type    = list(string)
  default = []
}

variable "sagemaker_endpoint_arns" {
  type    = list(string)
  default = []
}

variable "extra_environment" {
  type        = map(string)
  description = "Variables no secretas adicionales (p. ej. AI_PROVIDER_ORDER)."
  default     = {}
}

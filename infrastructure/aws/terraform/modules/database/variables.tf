variable "name" {
  type = string
}

variable "enabled" {
  type        = bool
  description = "false = no se crea nada (la app aún no usa PostgreSQL: ADR-0005)."
  default     = false
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subredes privadas."
}

variable "allowed_security_group_id" {
  type        = string
  description = "Único SG con acceso al puerto 5432 (el de las tareas de la app)."
}

variable "kms_key_arn" {
  type = string
}

variable "engine_version" {
  type        = string
  description = "VERIFY: versión de Aurora PostgreSQL disponible en la región."
  default     = "16.4"
}

variable "min_acu" {
  type    = number
  default = 0.5
}

variable "max_acu" {
  type    = number
  default = 2
}

variable "backup_retention_days" {
  type    = number
  default = 7
}

variable "deletion_protection" {
  type    = bool
  default = true
}

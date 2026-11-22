variable "name" {
  type        = string
  description = "Prefijo de nombres (p. ej. nexaro-dev)."
}

variable "cidr" {
  type        = string
  description = "CIDR de la VPC."
  default     = "10.20.0.0/16"
}

variable "az_count" {
  type        = number
  description = "Zonas de disponibilidad (2 mínimo para ALB y Aurora)."
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count debe ser 2 o 3."
  }
}

variable "enable_nat" {
  type        = bool
  description = "Una NAT Gateway (coste fijo + datos). Si es false, las tareas usan subredes públicas con SG cerrado."
  default     = false
}

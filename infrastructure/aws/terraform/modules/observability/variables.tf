variable "name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "alert_email" {
  type        = string
  description = "Correo para alarmas y avisos de presupuesto (hay que confirmar la suscripción SNS)."
}

variable "monthly_budget_usd" {
  type        = number
  description = "Presupuesto mensual. Avisa al 80 % real y al 100 % previsto. NO corta el gasto."
}

variable "alb_arn_suffix" {
  type = string
}

variable "target_group_arn_suffix" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "service_name" {
  type = string
}

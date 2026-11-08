variable "name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "force_destroy" {
  type        = bool
  description = "Permite borrar el bucket con objetos. Solo true en dev."
  default     = false
}

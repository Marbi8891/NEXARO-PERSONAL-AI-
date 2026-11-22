variable "name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "task_subnet_ids" {
  type        = list(string)
  description = "Subredes de las tareas (privadas con NAT, o públicas sin NAT)."
}

variable "assign_public_ip" {
  type        = bool
  description = "true solo cuando las tareas están en subredes públicas (sin NAT)."
}

variable "certificate_arn" {
  type        = string
  description = "Certificado ACM en la misma región. HTTPS es obligatorio: la app exige cookies Secure."
}

variable "image" {
  type        = string
  description = "URL del repositorio ECR con etiqueta inmutable (p. ej. ...:1.4.0). Nunca 'latest'."
}

variable "desired_count" {
  type        = number
  description = "0 mientras la app use SQLite local: en Fargate el disco es efímero (ADR-0005)."
  default     = 0
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "kms_key_arn" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "environment_variables" {
  type        = map(string)
  description = "Variables no secretas del contenedor."
  default     = {}
}

variable "documents_bucket_arn" {
  type = string
}

variable "bedrock_model_arns" {
  type        = list(string)
  description = "ARNs exactos de modelos de Bedrock permitidos (sin comodines). Vacío = sin acceso."
  default     = []
}

variable "sagemaker_endpoint_arns" {
  type        = list(string)
  description = "ARNs exactos de endpoints de SageMaker permitidos. Vacío = sin acceso."
  default     = []
}

variable "secret_arns" {
  type        = list(string)
  description = "Secretos de Secrets Manager que la tarea puede leer."
  default     = []
}

variable "vpc_cidr" {
  type = string
}

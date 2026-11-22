variable "region" {
  type        = string
  description = "VERIFY: comprueba la disponibilidad de Bedrock y de los modelos elegidos en la región."
  default     = "eu-west-1"
}

variable "alert_email" {
  type        = string
  description = "Correo para alarmas y avisos de presupuesto."
}

variable "certificate_arn" {
  type        = string
  description = "ARN del certificado ACM (misma región) del dominio de la aplicación."
}

variable "image_tag" {
  type        = string
  description = "Etiqueta inmutable de la imagen en ECR."
}

variable "allowed_origins" {
  type        = list(string)
  description = "Orígenes https permitidos, p. ej. [\"https://app.ejemplo.com\"]."
}

variable "bedrock_model_arns" {
  type        = list(string)
  description = "ARNs exactos de modelos de Bedrock permitidos. Vacío = sin acceso a Bedrock."
  default     = []
}

variable "sagemaker_endpoint_arns" {
  type        = list(string)
  description = "ARNs exactos de endpoints de SageMaker permitidos. Vacío = sin acceso."
  default     = []
}

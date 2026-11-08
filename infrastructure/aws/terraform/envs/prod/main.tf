terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70" # VERIFY: fijar la versión probada en el primer `init`
    }
  }

  # Configuración parcial: terraform init -backend-config=backend.hcl (ver backend.hcl.example)
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "nexaro"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

module "stack" {
  source = "../../modules/stack"

  environment = "prod"

  # Red
  enable_nat = true

  # Base de datos: false hasta que la aplicación pueda ejecutar sobre PostgreSQL (ADR-0005).
  enable_database      = false
  database_min_acu     = 1
  database_max_acu     = 8
  database_backup_days = 14
  deletion_protection  = true

  # Seguridad y coste
  enable_guardduty      = true
  enable_cloudtrail     = true
  force_destroy_buckets = false
  log_retention_days    = 90
  monthly_budget_usd    = 300
  alert_email           = var.alert_email

  # Aplicación. desired_count = 0: con SQLite local el disco de Fargate es efímero (ADR-0005).
  certificate_arn         = var.certificate_arn
  image_tag               = var.image_tag
  desired_count           = 0
  allowed_origins         = var.allowed_origins
  bedrock_model_arns      = var.bedrock_model_arns
  sagemaker_endpoint_arns = var.sagemaker_endpoint_arns
}

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
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

module "stack" {
  source = "../../modules/stack"

  environment = "dev"

  # Red
  enable_nat = false

  # Base de datos: false hasta que la aplicación pueda ejecutar sobre PostgreSQL (ADR-0005).
  enable_database      = false
  database_min_acu     = 0.5
  database_max_acu     = 2
  database_backup_days = 7
  deletion_protection  = false

  # Seguridad y coste
  enable_guardduty      = false
  enable_cloudtrail     = false
  force_destroy_buckets = true
  log_retention_days    = 14
  monthly_budget_usd    = 30
  alert_email           = var.alert_email

  # Aplicación. desired_count = 0: con SQLite local el disco de Fargate es efímero (ADR-0005).
  certificate_arn         = var.certificate_arn
  image_tag               = var.image_tag
  desired_count           = 0
  allowed_origins         = var.allowed_origins
  bedrock_model_arns      = var.bedrock_model_arns
  sagemaker_endpoint_arns = var.sagemaker_endpoint_arns
}

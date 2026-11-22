locals {
  name = "${var.project}-${var.environment}"
}

module "network" {
  source     = "../network"
  name       = local.name
  cidr       = var.vpc_cidr
  enable_nat = var.enable_nat
}

module "kms" {
  source = "../kms"
  name   = local.name
}

module "ecr" {
  source      = "../ecr"
  name        = local.name
  kms_key_arn = module.kms.key_arn
}

module "storage" {
  source        = "../storage"
  name          = local.name
  kms_key_arn   = module.kms.key_arn
  force_destroy = var.force_destroy_buckets
}

module "app" {
  source = "../app"

  name        = local.name
  environment = var.environment
  vpc_id      = module.network.vpc_id
  vpc_cidr    = module.network.vpc_cidr

  public_subnet_ids = module.network.public_subnet_ids
  task_subnet_ids   = module.network.uses_private_subnets ? module.network.private_subnet_ids : module.network.public_subnet_ids
  assign_public_ip  = !module.network.uses_private_subnets

  certificate_arn = var.certificate_arn
  image           = "${module.ecr.repository_url}:${var.image_tag}"
  desired_count   = var.desired_count
  kms_key_arn     = module.kms.key_arn

  log_retention_days      = var.log_retention_days
  documents_bucket_arn    = module.storage.bucket_arn
  bedrock_model_arns      = var.bedrock_model_arns
  sagemaker_endpoint_arns = var.sagemaker_endpoint_arns

  environment_variables = merge(
    {
      NEXARO_ENV      = var.environment == "prod" ? "production" : "staging"
      COOKIE_SECURE   = "true"
      ALLOWED_ORIGINS = join(",", var.allowed_origins)
    },
    var.extra_environment,
  )
}

module "database" {
  source = "../database"

  name                      = local.name
  enabled                   = var.enable_database
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_subnet_ids
  allowed_security_group_id = module.app.tasks_security_group_id
  kms_key_arn               = module.kms.key_arn
  min_acu                   = var.database_min_acu
  max_acu                   = var.database_max_acu
  backup_retention_days     = var.database_backup_days
  deletion_protection       = var.deletion_protection
}

module "observability" {
  source = "../observability"

  name                    = local.name
  kms_key_arn             = module.kms.key_arn
  alert_email             = var.alert_email
  monthly_budget_usd      = var.monthly_budget_usd
  alb_arn_suffix          = module.app.alb_arn_suffix
  target_group_arn_suffix = module.app.target_group_arn_suffix
  cluster_name            = module.app.cluster_name
  service_name            = module.app.service_name
}

module "security_baseline" {
  source = "../security_baseline"

  name              = local.name
  kms_key_arn       = module.kms.key_arn
  enable_guardduty  = var.enable_guardduty
  enable_cloudtrail = var.enable_cloudtrail
}

resource "aws_db_subnet_group" "this" {
  count      = var.enabled ? 1 : 0
  name       = var.name
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "db" {
  count       = var.enabled ? 1 : 0
  name        = "${var.name}-db"
  description = "PostgreSQL: solo desde las tareas de la aplicación"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "from_app" {
  count                        = var.enabled ? 1 : 0
  security_group_id            = aws_security_group.db[0].id
  referenced_security_group_id = var.allowed_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL desde la aplicación"
}

resource "aws_rds_cluster" "this" {
  count              = var.enabled ? 1 : 0
  cluster_identifier = var.name
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = var.engine_version
  database_name      = "nexaro"
  master_username    = "nexaro_admin"

  # La contraseña maestra la genera y rota AWS en Secrets Manager: no pasa por el estado ni el repo.
  manage_master_user_password   = true
  master_user_secret_kms_key_id = var.kms_key_arn

  storage_encrypted                   = true
  kms_key_id                          = var.kms_key_arn
  iam_database_authentication_enabled = true
  db_subnet_group_name                = aws_db_subnet_group.this[0].name
  vpc_security_group_ids              = [aws_security_group.db[0].id]

  backup_retention_period         = var.backup_retention_days
  preferred_backup_window         = "02:00-03:00"
  deletion_protection             = var.deletion_protection
  skip_final_snapshot             = !var.deletion_protection
  final_snapshot_identifier       = var.deletion_protection ? "${var.name}-final" : null
  copy_tags_to_snapshot           = true
  enabled_cloudwatch_logs_exports = ["postgresql"]

  serverlessv2_scaling_configuration {
    min_capacity = var.min_acu
    max_capacity = var.max_acu
  }
}

resource "aws_rds_cluster_instance" "this" {
  count              = var.enabled ? 1 : 0
  identifier         = "${var.name}-1"
  cluster_identifier = aws_rds_cluster.this[0].id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.this[0].engine
  engine_version     = aws_rds_cluster.this[0].engine_version
}

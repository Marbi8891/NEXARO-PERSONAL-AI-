output "endpoint" {
  value = var.enabled ? aws_rds_cluster.this[0].endpoint : null
}

output "master_secret_arn" {
  description = "Secreto gestionado por AWS con las credenciales maestras (solo para migraciones/rol de la app)."
  value       = var.enabled ? aws_rds_cluster.this[0].master_user_secret[0].secret_arn : null
}

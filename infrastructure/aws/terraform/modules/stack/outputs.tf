output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "alb_dns_name" {
  description = "Apunta aquí el CNAME/alias del dominio de la aplicación."
  value       = module.app.alb_dns_name
}

output "documents_bucket" {
  value = module.storage.bucket_name
}

output "database_endpoint" {
  value = module.database.endpoint
}

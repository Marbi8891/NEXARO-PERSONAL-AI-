output "ecr_repository_url" {
  value = module.stack.ecr_repository_url
}

output "alb_dns_name" {
  value = module.stack.alb_dns_name
}

output "documents_bucket" {
  value = module.stack.documents_bucket
}

output "database_endpoint" {
  value = module.stack.database_endpoint
}

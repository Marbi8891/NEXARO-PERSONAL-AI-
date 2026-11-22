output "vpc_id" {
  value = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "uses_private_subnets" {
  description = "true si hay NAT y las tareas pueden vivir en subredes privadas."
  value       = var.enable_nat
}

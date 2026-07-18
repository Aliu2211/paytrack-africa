output "tenants_table_name" {
  value = aws_dynamodb_table.tenants.name
}

output "tenants_table_arn" {
  value = aws_dynamodb_table.tenants.arn
}

output "invoices_table_name" {
  value = aws_dynamodb_table.invoices.name
}

output "invoices_table_arn" {
  value = aws_dynamodb_table.invoices.arn
}

output "api_url" {
  value = module.api_gateway.api_url
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_client_id" {
  value = module.cognito.user_pool_client_id
}

output "invoices_table_name" {
  value = module.dynamodb.invoices_table_name
}

output "tenants_table_name" {
  value = module.dynamodb.tenants_table_name
}

output "github_oidc_role_arn" {
  value = module.github_oidc.role_arn
}

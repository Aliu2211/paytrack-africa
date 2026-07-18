variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "cognito_user_pool_arn" {
  type = string
}

variable "lambda_invoke_arns" {
  type        = map(string)
  description = "Map of function key (invoice_create, invoice_get, invoice_list, invoice_update) to Lambda invoke ARN"
}

variable "lambda_function_names" {
  type        = map(string)
  description = "Map of function key to deployed Lambda function name"
}

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "engineering_alert_email" {
  type        = string
  description = "Email address subscribed to the engineering alerts SNS topic"
}

variable "lambda_function_names" {
  type        = map(string)
  description = "Map of short function key (e.g. invoice_create) to deployed Lambda function name"
}

variable "api_gateway_name" {
  type        = string
  description = "REST API name, used as the AWS/ApiGateway CloudWatch dimension"
}

variable "api_gateway_stage_name" {
  type = string
}

variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "tenants_table_name" {
  type = string
}

variable "tenants_table_arn" {
  type = string
}

variable "invoices_table_name" {
  type = string
}

variable "invoices_table_arn" {
  type = string
}

variable "function_names" {
  type        = list(string)
  description = "Lambda function names to create, one per functions/<name> directory"
  default     = ["invoice_create", "invoice_get", "invoice_list", "invoice_update"]
}

variable "sns_topic_arn" {
  type        = string
  description = "SNS topic ARN for payment reminder publishes"
}

variable "ses_sender_email" {
  type        = string
  description = "Verified SES sender email used by payment_reminder"
}

variable "pdf_bucket_name" {
  type        = string
  description = "S3 bucket name for generated invoice PDFs"
}

variable "pdf_bucket_arn" {
  type        = string
  description = "S3 bucket ARN for generated invoice PDFs"
}

variable "gemini_secret_arn" {
  type        = string
  description = "Secrets Manager ARN holding the Gemini API key"
}

variable "invoices_stream_arn" {
  type        = string
  description = "DynamoDB Streams ARN for the invoices table"
}

variable "analytics_table_name" {
  type        = string
  description = "Analytics DynamoDB table name"
}

variable "analytics_table_arn" {
  type        = string
  description = "Analytics DynamoDB table ARN"
}

variable "cognito_user_pool_id" {
  type        = string
  description = "Cognito user pool ID, for weekly_report's tenant email lookup"
}

variable "cognito_user_pool_arn" {
  type        = string
  description = "Cognito user pool ARN, to scope weekly_report's ListUsers permission"
}

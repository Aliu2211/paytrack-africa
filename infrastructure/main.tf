module "dynamodb" {
  source = "./modules/dynamodb"

  project_name = var.project_name
  environment  = var.environment
}

module "cognito" {
  source = "./modules/cognito"

  user_pool_name = var.cognito_user_pool_name
}

module "sns" {
  source = "./modules/sns"

  project_name = var.project_name
  environment  = var.environment
}

module "ses" {
  source = "./modules/ses"

  sender_email = var.ses_sender_email
}

module "s3_pdf" {
  source = "./modules/s3_pdf"

  project_name = var.project_name
  environment  = var.environment
}

data "aws_secretsmanager_secret" "gemini_api_key" {
  name = "paytrack/gemini-api-key"
}

module "lambda" {
  source = "./modules/lambda"

  project_name = var.project_name
  environment  = var.environment

  tenants_table_name  = module.dynamodb.tenants_table_name
  tenants_table_arn   = module.dynamodb.tenants_table_arn
  invoices_table_name = module.dynamodb.invoices_table_name
  invoices_table_arn  = module.dynamodb.invoices_table_arn

  function_names = [
    "invoice_create",
    "invoice_get",
    "invoice_list",
    "invoice_update",
    "payment_reminder",
    "ai_collections",
    "invoice_pdf",
    "analytics",
    "weekly_report",
  ]

  sns_topic_arn     = module.sns.topic_arn
  ses_sender_email  = module.ses.sender_email
  pdf_bucket_name   = module.s3_pdf.bucket_name
  pdf_bucket_arn    = module.s3_pdf.bucket_arn
  gemini_secret_arn = data.aws_secretsmanager_secret.gemini_api_key.arn

  invoices_stream_arn   = module.dynamodb.invoices_stream_arn
  analytics_table_name  = module.dynamodb.analytics_table_name
  analytics_table_arn   = module.dynamodb.analytics_table_arn
  cognito_user_pool_id  = module.cognito.user_pool_id
  cognito_user_pool_arn = module.cognito.user_pool_arn
}

resource "aws_lambda_event_source_mapping" "analytics_stream" {
  event_source_arn  = module.dynamodb.invoices_stream_arn
  function_name     = module.lambda.function_arns["analytics"]
  starting_position = "LATEST"
}

module "api_gateway" {
  source = "./modules/api_gateway"

  project_name          = var.project_name
  environment           = var.environment
  cognito_user_pool_arn = module.cognito.user_pool_arn
  lambda_invoke_arns    = module.lambda.function_invoke_arns
  lambda_function_names = module.lambda.function_names
}

module "eventbridge" {
  source = "./modules/eventbridge"

  project_name = var.project_name
  environment  = var.environment

  payment_reminder_function_arn  = module.lambda.function_arns["payment_reminder"]
  payment_reminder_function_name = module.lambda.function_names["payment_reminder"]

  weekly_report_function_arn  = module.lambda.function_arns["weekly_report"]
  weekly_report_function_name = module.lambda.function_names["weekly_report"]
}

module "cloudwatch" {
  source = "./modules/cloudwatch"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  engineering_alert_email = var.engineering_alert_email
  lambda_function_names   = module.lambda.function_names
  api_gateway_name        = "${var.project_name}-api-${var.environment}"
  api_gateway_stage_name  = var.environment

  depends_on = [module.api_gateway]
}

data "aws_caller_identity" "current" {}

module "github_oidc" {
  source = "./modules/github_oidc"

  project_name = var.project_name
  environment  = var.environment
  github_repo  = var.github_repo

  state_bucket_arn     = "arn:aws:s3:::${var.state_bucket_name}"
  state_lock_table_arn = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/paytrack-tf-lock"
}

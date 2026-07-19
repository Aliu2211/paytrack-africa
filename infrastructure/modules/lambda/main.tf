data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.project_name}-lambda-exec-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "dynamodb_access" {
  statement {
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      var.tenants_table_arn,
      var.invoices_table_arn,
      "${var.invoices_table_arn}/index/*",
    ]
  }
}

resource "aws_iam_role_policy" "dynamodb_access" {
  name   = "${var.project_name}-lambda-dynamodb-${var.environment}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.dynamodb_access.json
}

data "aws_iam_policy_document" "sns_publish" {
  statement {
    actions   = ["sns:Publish"]
    resources = [var.sns_topic_arn]
  }
}

resource "aws_iam_role_policy" "sns_publish" {
  name   = "${var.project_name}-lambda-sns-${var.environment}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.sns_publish.json
}

data "aws_iam_policy_document" "ses_send" {
  statement {
    # SES does not support resource-level ARNs for SendEmail.
    actions   = ["ses:SendEmail"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ses_send" {
  name   = "${var.project_name}-lambda-ses-${var.environment}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.ses_send.json
}

data "aws_iam_policy_document" "pdf_bucket_access" {
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${var.pdf_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "pdf_bucket_access" {
  name   = "${var.project_name}-lambda-s3-pdf-${var.environment}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.pdf_bucket_access.json
}

data "aws_iam_policy_document" "gemini_secret_access" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.gemini_secret_arn]
  }
}

resource "aws_iam_role_policy" "gemini_secret_access" {
  name   = "${var.project_name}-lambda-secrets-${var.environment}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.gemini_secret_access.json
}

data "aws_iam_policy_document" "xray_tracing" {
  statement {
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "xray_tracing" {
  name   = "${var.project_name}-lambda-xray-${var.environment}"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.xray_tracing.json
}

locals {
  common_env_vars = {
    INVOICES_TABLE = var.invoices_table_name
    TENANTS_TABLE  = var.tenants_table_name
    ENVIRONMENT    = var.environment
  }

  # Extra env vars only the Phase 2 functions need. Merged onto the common
  # set below rather than restructuring the for_each per function.
  function_env_vars = {
    payment_reminder = {
      SNS_TOPIC_ARN    = var.sns_topic_arn
      SES_SENDER_EMAIL = var.ses_sender_email
    }
    ai_collections = {
      GEMINI_SECRET_ARN = var.gemini_secret_arn
    }
    invoice_pdf = {
      PDF_BUCKET_NAME = var.pdf_bucket_name
    }
  }
}

resource "aws_s3_bucket" "deployments" {
  bucket        = "${var.project_name}-lambda-deployments-${var.environment}"
  force_destroy = true
}

resource "aws_s3_object" "this" {
  for_each = toset(var.function_names)

  bucket = aws_s3_bucket.deployments.id
  key    = "${each.value}.zip"
  # path.module anchors this to modules/lambda/ regardless of the directory
  # terraform is invoked from; a bare "../packages/..." resolves relative to
  # the CWD instead and points one level too high once this is a submodule.
  source = "${path.module}/../../packages/${each.value}.zip"
  etag   = filemd5("${path.module}/../../packages/${each.value}.zip")
}

resource "aws_lambda_function" "this" {
  for_each = toset(var.function_names)

  function_name = "${var.project_name}-${each.value}-${var.environment}"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  memory_size   = 256
  timeout       = 30

  # Deploying via S3 rather than a direct inline upload -- CreateFunction's
  # inline ZipFile path signs the whole multi-MB payload as one request, and
  # on a slow connection that upload can outlast the signature's validity
  # window (observed: a 33MB package took >17min and failed with
  # InvalidSignatureException). S3 uploads don't have that constraint.
  s3_bucket        = aws_s3_bucket.deployments.id
  s3_key           = aws_s3_object.this[each.value].key
  source_code_hash = filebase64sha256("${path.module}/../../packages/${each.value}.zip")

  environment {
    variables = merge(local.common_env_vars, lookup(local.function_env_vars, each.value, {}))
  }

  tracing_config {
    mode = "PassThrough"
  }

  depends_on = [aws_s3_object.this]
}

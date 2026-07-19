resource "aws_api_gateway_rest_api" "this" {
  name = "${var.project_name}-api-${var.environment}"
}

resource "aws_api_gateway_authorizer" "cognito" {
  name            = "${var.project_name}-cognito-authorizer-${var.environment}"
  rest_api_id     = aws_api_gateway_rest_api.this.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [var.cognito_user_pool_arn]
  identity_source = "method.request.header.Authorization"
}

resource "aws_api_gateway_resource" "invoices" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "invoices"
}

resource "aws_api_gateway_resource" "invoice_id" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.invoices.id
  path_part   = "{id}"
}

resource "aws_api_gateway_resource" "invoice_collect" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.invoice_id.id
  path_part   = "collect"
}

resource "aws_api_gateway_resource" "invoice_pdf" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.invoice_id.id
  path_part   = "pdf"
}

locals {
  routes = {
    invoice_create = { resource_id = aws_api_gateway_resource.invoices.id, http_method = "POST", function_key = "invoice_create" }
    invoice_list   = { resource_id = aws_api_gateway_resource.invoices.id, http_method = "GET", function_key = "invoice_list" }
    invoice_get    = { resource_id = aws_api_gateway_resource.invoice_id.id, http_method = "GET", function_key = "invoice_get" }
    invoice_update = { resource_id = aws_api_gateway_resource.invoice_id.id, http_method = "PUT", function_key = "invoice_update" }
    ai_collections = { resource_id = aws_api_gateway_resource.invoice_collect.id, http_method = "POST", function_key = "ai_collections" }
    invoice_pdf    = { resource_id = aws_api_gateway_resource.invoice_pdf.id, http_method = "POST", function_key = "invoice_pdf" }
  }
}

resource "aws_api_gateway_method" "this" {
  for_each = local.routes

  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = each.value.resource_id
  http_method   = each.value.http_method
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "this" {
  for_each = local.routes

  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = each.value.resource_id
  http_method             = aws_api_gateway_method.this[each.key].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arns[each.value.function_key]
}

resource "aws_lambda_permission" "apigw" {
  for_each = local.routes

  statement_id  = "AllowAPIGatewayInvoke${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_names[each.value.function_key]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/*"
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.invoices.id,
      aws_api_gateway_resource.invoice_id.id,
      aws_api_gateway_resource.invoice_collect.id,
      aws_api_gateway_resource.invoice_pdf.id,
      [for k, v in aws_api_gateway_method.this : v.id],
      [for k, v in aws_api_gateway_integration.this : v.id],
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_api_gateway_integration.this]
}

resource "aws_api_gateway_stage" "this" {
  deployment_id        = aws_api_gateway_deployment.this.id
  rest_api_id          = aws_api_gateway_rest_api.this.id
  stage_name           = var.environment
  xray_tracing_enabled = true
}

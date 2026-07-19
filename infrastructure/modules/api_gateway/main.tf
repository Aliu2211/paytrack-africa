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

# API Gateway's own error responses (401 from the authorizer, 403/404 route
# errors, 502 on a Lambda crash, etc.) come from API Gateway itself, not the
# Lambda -- they don't carry whatever headers the Lambda sets. Without CORS
# headers here too, any of these get reported to the browser as a CORS
# failure, masking the real error (this is exactly how a 502 from an
# unhandled Lambda exception showed up as "blocked by CORS policy").
resource "aws_api_gateway_gateway_response" "default_4xx" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "DEFAULT_4XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
  }
}

resource "aws_api_gateway_gateway_response" "default_5xx" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "DEFAULT_5XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
  }
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

# The dashboard runs on a different origin (localhost:3000 in dev) than the
# API, and sends a custom Authorization header, so the browser preflights
# every request with OPTIONS. Without these, the browser blocks the actual
# request before it's even sent -- curl-based testing never surfaced this
# since curl isn't subject to CORS.
locals {
  cors_resources = {
    invoices        = aws_api_gateway_resource.invoices.id
    invoice_id      = aws_api_gateway_resource.invoice_id.id
    invoice_collect = aws_api_gateway_resource.invoice_collect.id
    invoice_pdf     = aws_api_gateway_resource.invoice_pdf.id
  }
}

resource "aws_api_gateway_method" "options" {
  for_each = local.cors_resources

  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = each.value
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "options" {
  for_each = local.cors_resources

  rest_api_id = aws_api_gateway_rest_api.this.id
  resource_id = each.value
  http_method = aws_api_gateway_method.options[each.key].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "options" {
  for_each = local.cors_resources

  rest_api_id = aws_api_gateway_rest_api.this.id
  resource_id = each.value
  http_method = aws_api_gateway_method.options[each.key].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "options" {
  for_each = local.cors_resources

  rest_api_id = aws_api_gateway_rest_api.this.id
  resource_id = each.value
  http_method = aws_api_gateway_method.options[each.key].http_method
  status_code = aws_api_gateway_method_response.options[each.key].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }

  depends_on = [aws_api_gateway_integration.options]
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
      [for k, v in aws_api_gateway_method.options : v.id],
      [for k, v in aws_api_gateway_integration_response.options : v.id],
      aws_api_gateway_gateway_response.default_4xx.id,
      aws_api_gateway_gateway_response.default_5xx.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_api_gateway_integration.this, aws_api_gateway_integration_response.options]
}

resource "aws_api_gateway_stage" "this" {
  deployment_id        = aws_api_gateway_deployment.this.id
  rest_api_id          = aws_api_gateway_rest_api.this.id
  stage_name           = var.environment
  xray_tracing_enabled = true
}

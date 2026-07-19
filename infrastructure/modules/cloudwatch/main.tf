resource "aws_sns_topic" "engineering_alerts" {
  name = "${var.project_name}-engineering-alerts-${var.environment}"
}

resource "aws_sns_topic_subscription" "engineering_alerts_email" {
  topic_arn = aws_sns_topic.engineering_alerts.arn
  protocol  = "email"
  endpoint  = var.engineering_alert_email
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = var.lambda_function_names

  alarm_name          = "${var.project_name}-${each.key}-errors-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.engineering_alerts.arn]

  dimensions = {
    FunctionName = each.value
  }
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration_p95" {
  for_each = var.lambda_function_names

  alarm_name          = "${var.project_name}-${each.key}-duration-p95-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  extended_statistic  = "p95"
  threshold           = 3000
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.engineering_alerts.arn]

  dimensions = {
    FunctionName = each.value
  }
}

resource "aws_cloudwatch_metric_alarm" "api_gateway_4xx_rate" {
  alarm_name          = "${var.project_name}-api-4xx-rate-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 10
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.engineering_alerts.arn]

  metric_query {
    id          = "rate"
    expression  = "(errors / requests) * 100"
    label       = "4xx error rate (%)"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      metric_name = "4XXError"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions = {
        ApiName = var.api_gateway_name
        Stage   = var.api_gateway_stage_name
      }
    }
  }

  metric_query {
    id = "requests"
    metric {
      metric_name = "Count"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions = {
        ApiName = var.api_gateway_name
        Stage   = var.api_gateway_stage_name
      }
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "api_gateway_5xx_rate" {
  alarm_name          = "${var.project_name}-api-5xx-rate-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.engineering_alerts.arn]

  metric_query {
    id          = "rate"
    expression  = "(errors / requests) * 100"
    label       = "5xx error rate (%)"
    return_data = true
  }

  metric_query {
    id = "errors"
    metric {
      metric_name = "5XXError"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions = {
        ApiName = var.api_gateway_name
        Stage   = var.api_gateway_stage_name
      }
    }
  }

  metric_query {
    id = "requests"
    metric {
      metric_name = "Count"
      namespace   = "AWS/ApiGateway"
      period      = 300
      stat        = "Sum"
      dimensions = {
        ApiName = var.api_gateway_name
        Stage   = var.api_gateway_stage_name
      }
    }
  }
}

locals {
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Lambda Invocations"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 3600
          metrics = [for name in values(var.lambda_function_names) : ["AWS/Lambda", "Invocations", "FunctionName", name]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Lambda Errors"
          view    = "bar"
          region  = var.aws_region
          period  = 3600
          metrics = [for name in values(var.lambda_function_names) : ["AWS/Lambda", "Errors", "FunctionName", name]]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "Lambda P95 Duration"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 3600
          metrics = [for name in values(var.lambda_function_names) : ["AWS/Lambda", "Duration", "FunctionName", name, { stat = "p95" }]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 6
        height = 6
        properties = {
          title   = "API Gateway 4xx Count"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 3600
          metrics = [["AWS/ApiGateway", "4XXError", "ApiName", var.api_gateway_name, "Stage", var.api_gateway_stage_name, { stat = "Sum" }]]
        }
      },
      {
        type   = "metric"
        x      = 18
        y      = 6
        width  = 6
        height = 6
        properties = {
          title   = "API Gateway 5xx Count"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 3600
          metrics = [["AWS/ApiGateway", "5XXError", "ApiName", var.api_gateway_name, "Stage", var.api_gateway_stage_name, { stat = "Sum" }]]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title   = "API Gateway Latency P95"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 3600
          metrics = [["AWS/ApiGateway", "Latency", "ApiName", var.api_gateway_name, "Stage", var.api_gateway_stage_name, { stat = "p95" }]]
        }
      },
    ]
  })
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = "${var.project_name}-${var.environment}"
  dashboard_body = local.dashboard_body
}

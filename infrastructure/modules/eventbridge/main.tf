resource "aws_cloudwatch_event_rule" "daily_reminder" {
  name                = "${var.project_name}-daily-reminder-${var.environment}"
  schedule_expression = "cron(0 8 * * ? *)"
}

resource "aws_cloudwatch_event_target" "payment_reminder" {
  rule = aws_cloudwatch_event_rule.daily_reminder.name
  arn  = var.payment_reminder_function_arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.payment_reminder_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_reminder.arn
}

resource "aws_cloudwatch_event_rule" "weekly_report" {
  name                = "${var.project_name}-weekly-report-${var.environment}"
  schedule_expression = "cron(0 9 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "weekly_report" {
  rule = aws_cloudwatch_event_rule.weekly_report.name
  arn  = var.weekly_report_function_arn
}

resource "aws_lambda_permission" "eventbridge_weekly_report" {
  statement_id  = "AllowEventBridgeInvokeWeeklyReport"
  action        = "lambda:InvokeFunction"
  function_name = var.weekly_report_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_report.arn
}

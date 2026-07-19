output "alerts_topic_arn" {
  value = aws_sns_topic.engineering_alerts.arn
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.this.dashboard_name
}

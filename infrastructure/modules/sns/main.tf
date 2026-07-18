resource "aws_sns_topic" "payment_reminders" {
  name = "${var.project_name}-payment-reminders-${var.environment}"
}

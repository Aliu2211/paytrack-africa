resource "aws_dynamodb_table" "tenants" {
  name         = "${var.project_name}-tenants-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tenant_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_dynamodb_table" "invoices" {
  name         = "${var.project_name}-invoices-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tenant_id"
  range_key    = "invoice_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "invoice_id"
    type = "S"
  }

  attribute {
    name = "due_date"
    type = "S"
  }

  global_secondary_index {
    name            = "status-due-date-index"
    hash_key        = "tenant_id"
    range_key       = "due_date"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"
}

resource "aws_dynamodb_table" "analytics" {
  name         = "${var.project_name}-analytics-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tenant_id"
  range_key    = "metric_key"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "metric_key"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

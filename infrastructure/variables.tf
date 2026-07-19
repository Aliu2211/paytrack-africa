variable "aws_region" {
  type        = string
  description = "AWS region for all resources"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Deployment environment name"
  default     = "dev"
}

variable "project_name" {
  type        = string
  description = "Project name used as a resource naming prefix"
  default     = "paytrack"
}

variable "state_bucket_name" {
  type        = string
  description = "S3 bucket name used for Terraform remote state"
}

variable "cognito_user_pool_name" {
  type        = string
  description = "Name of the Cognito user pool"
  default     = "paytrack-sme-users"
}

variable "ses_sender_email" {
  type        = string
  description = "Verified SES sender identity for reminder and collections emails"
  default     = "aliutijani21@gmail.com"
}

variable "engineering_alert_email" {
  type        = string
  description = "Email subscribed to the engineering alerts SNS topic for CloudWatch alarms"
  default     = "aliutijani21@gmail.com"
}

variable "github_repo" {
  type        = string
  description = "GitHub repo in owner/name form, used to scope the CI OIDC role's trust policy"
  default     = "Aliu2211/paytrack-africa"
}

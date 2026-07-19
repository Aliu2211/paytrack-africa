variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "github_repo" {
  type        = string
  description = "GitHub repo in owner/name form, e.g. Aliu2211/paytrack-africa"
}

variable "state_bucket_arn" {
  type = string
}

variable "state_lock_table_arn" {
  type = string
}

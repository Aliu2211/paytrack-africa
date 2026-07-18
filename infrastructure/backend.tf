terraform {
  backend "s3" {
    bucket         = "paytrack-tf-state-2026"
    key            = "paytrack/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "paytrack-tf-lock"
  }
}

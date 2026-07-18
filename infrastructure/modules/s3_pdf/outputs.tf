output "bucket_name" {
  value = aws_s3_bucket.pdfs.id
}

output "bucket_arn" {
  value = aws_s3_bucket.pdfs.arn
}

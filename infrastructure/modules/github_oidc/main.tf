# An OIDC provider for token.actions.githubusercontent.com already exists in
# this account (from a prior project) -- reused via data source rather than
# creating a duplicate, since the provider URL must be unique per account.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # GitHub's sub claim isn't the plain "repo:OWNER/REPO:ref:..." format
    # AWS's own docs show as the example -- it inlines immutable numeric IDs
    # after the owner and repo name (confirmed by decoding a real token in
    # CI): "repo:Aliu2211@117759265/paytrack-africa@1305285531:ref:refs/heads/main".
    # A plain StringEquals/StringLike on the literal owner/repo string never
    # matches because of the "@<id>" segments, which is what caused every
    # attempt to fail with a generic AccessDenied that gave no hint why.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${split("/", var.github_repo)[0]}@*/${split("/", var.github_repo)[1]}@*:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-github-actions-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

# Service-level access for everything Terraform manages in this project.
# Not hand-scoped to individual resource ARNs -- for a portfolio project
# the maintenance cost of keeping fine-grained per-action policies in sync
# with every module change isn't worth it. IAM itself is the exception
# (below): letting CI create/attach arbitrary IAM policies unscoped would
# be a real privilege-escalation path, so that one is restricted to
# paytrack-named resources only.
locals {
  managed_policy_arns = [
    "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    "arn:aws:iam::aws:policy/AWSLambda_FullAccess",
    "arn:aws:iam::aws:policy/AmazonAPIGatewayAdministrator",
    "arn:aws:iam::aws:policy/AmazonCognitoPowerUser",
    "arn:aws:iam::aws:policy/AmazonS3FullAccess",
    "arn:aws:iam::aws:policy/AmazonSNSFullAccess",
    "arn:aws:iam::aws:policy/AmazonSESFullAccess",
    "arn:aws:iam::aws:policy/AmazonEventBridgeFullAccess",
    "arn:aws:iam::aws:policy/CloudWatchFullAccess",
    "arn:aws:iam::aws:policy/AWSXrayFullAccess",
  ]
}

resource "aws_iam_role_policy_attachment" "managed" {
  for_each = toset(local.managed_policy_arns)

  role       = aws_iam_role.github_actions.name
  policy_arn = each.value
}

data "aws_iam_policy_document" "scoped_iam" {
  statement {
    sid = "ManagePaytrackRoles"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:PassRole",
      "iam:TagRole",
    ]
    resources = ["arn:aws:iam::*:role/${var.project_name}-*"]
  }

  statement {
    sid = "ReadGeminiSecret"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
      "secretsmanager:GetResourcePolicy",
    ]
    resources = ["arn:aws:secretsmanager:*:*:secret:${var.project_name}/*"]
  }

  # Needed just to read the OIDC provider this role's own trust policy is
  # scoped to -- Terraform's data source lookup for it (main.tf) runs under
  # this role's credentials in CI, not the identity that created the
  # provider, so it needs its own explicit read permission.
  statement {
    sid       = "ReadGithubOidcProvider"
    actions   = ["iam:GetOpenIDConnectProvider"]
    resources = [data.aws_iam_openid_connect_provider.github.arn]
  }

  statement {
    sid       = "TerraformStateBucket"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [var.state_bucket_arn, "${var.state_bucket_arn}/*"]
  }

  statement {
    sid       = "TerraformStateLock"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = [var.state_lock_table_arn]
  }
}

resource "aws_iam_role_policy" "scoped" {
  name   = "${var.project_name}-github-actions-scoped-${var.environment}"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.scoped_iam.json
}

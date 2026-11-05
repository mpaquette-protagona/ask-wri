# Provider setup and shared values for the AskWRI infrastructure.
terraform {
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

# No profile or region is named here: Terraform uses your AWS_PROFILE and your profile's region
# (or AWS_DEFAULT_REGION). It must be a US region (see the check in storage.tf).
provider "aws" {}

# The region Terraform is deploying into
data "aws_region" "current" {}

locals {
  source_bucket   = "wri-publications"
  sections_bucket = "askwri-sections-${data.aws_caller_identity.me.account_id}"
}

# Used to build the account-specific bucket name and ARNs
data "aws_caller_identity" "me" {}

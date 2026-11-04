# Provider setup and shared values for the AskWRI infrastructure.
terraform {
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

# No profile is named here: Terraform uses the profile in your AWS_PROFILE environment variable
# (or your default profile).
provider "aws" {
  region = "us-east-1"
}

locals {
  source_bucket   = "wri-bucket-6157-5871-0841"
  sections_bucket = "askwri-sections-${data.aws_caller_identity.me.account_id}"
}

# Used to build the account-specific bucket name and ARNs
data "aws_caller_identity" "me" {}

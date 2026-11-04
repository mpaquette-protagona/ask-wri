# Provider setup and shared values for the AskWRI infrastructure.
terraform {
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

provider "aws" {
  region  = "us-east-1"
}

locals {
  source_bucket   = "wri-publications"
  sections_bucket = "askwri-sections-${data.aws_caller_identity.me.account_id}"
}

# Used to build the account-specific bucket name and ARNs
data "aws_caller_identity" "me" {}

# Provider setup and shared values for the AskWRI infrastructure.
terraform {
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

provider "aws" {
  region  = "us-east-1"
  profile = "builder"
}

# Name of the role the AgentCore deploy created (the agent runs as this role).
# Leave empty on the first apply; fill it in (terraform.tfvars) after deploying the agent.
variable "agent_role_name" {
  default = ""
}

locals {
  source_bucket   = "wri-bucket-6157-5871-0841"
  sections_bucket = "askwri-sections-${data.aws_caller_identity.me.account_id}"
}

# Used to build the account-specific bucket name and ARNs
data "aws_caller_identity" "me" {}

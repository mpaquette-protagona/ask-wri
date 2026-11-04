# The chat agent on AgentCore: code bucket, IAM role and the runtime itself.
# Build the zip first:  python agent/build_zip.py

# Bucket that holds the zipped agent code (versioned, so a new zip triggers a redeploy)
resource "aws_s3_bucket" "agent_code" {
  bucket        = "askwri-agent-code-${data.aws_caller_identity.me.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "agent_code" {
  bucket = aws_s3_bucket.agent_code.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_object" "agent_code" {
  bucket      = aws_s3_bucket.agent_code.id
  key         = "agent_code.zip"
  source      = "${path.module}/../agent/agent_code.zip"
  source_hash = filemd5("${path.module}/../agent/agent_code.zip") # re-upload only when the zip changes
  depends_on  = [aws_s3_bucket_versioning.agent_code]
}

# The role the agent runs as
resource "aws_iam_role" "agent" {
  name = "askwri-agent-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
    }]
  })
}

# What the agent may do: run the chat model, read our data, write logs
resource "aws_iam_role_policy" "agent" {
  name = "askwri-agent-access"
  role = aws_iam_role.agent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3vectors:QueryVectors", "s3vectors:GetVectors"]
        Resource = aws_s3vectors_index.chunks.index_arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Scan"]
        Resource = aws_dynamodb_table.documents.arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.sections.arn}/*", "${aws_s3_bucket.agent_code.arn}/*"]
      },
      {
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
        "logs:DescribeLogGroups", "logs:DescribeLogStreams"]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.me.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
      },
      {
        Effect = "Allow"
        Action = ["bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
        "bedrock-agentcore:GetWorkloadAccessTokenForUserId"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "cloudwatch:PutMetricData"]
        Resource = "*"
      },
    ]
  })
}

# The AgentCore runtime, started from the zip
resource "aws_bedrockagentcore_agent_runtime" "agent" {
  agent_runtime_name = "askwri_agent"
  role_arn           = aws_iam_role.agent.arn
  depends_on         = [aws_iam_role_policy.agent]

  agent_runtime_artifact {
    code_configuration {
      entry_point = ["agent.py"]
      runtime     = "PYTHON_3_12"
      code {
        s3 {
          bucket     = aws_s3_bucket.agent_code.id
          prefix     = aws_s3_object.agent_code.key
          version_id = aws_s3_object.agent_code.version_id
        }
      }
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }
}

# Copy this into AGENT_ARN in app/streamlit_app.py
output "agent_runtime_arn" {
  value = aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn
}

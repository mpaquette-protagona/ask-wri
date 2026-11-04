# Gives the AgentCore agent permission to read our data (search, sections, documents).
# Only created once agent_role_name is set, because that role exists only after the agent is deployed.
moved {
  from = aws_iam_role_policy.agent_data_access
  to   = aws_iam_role_policy.agent_data_access[0]
}

resource "aws_iam_role_policy" "agent_data_access" {
  count = var.agent_role_name == "" ? 0 : 1
  name  = "askwri-data-access"
  role = var.agent_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
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
        Resource = "${aws_s3_bucket.sections.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
      },
    ]
  })
}

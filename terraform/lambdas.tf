# The two ingestion Lambdas, their permissions, and the SQS triggers.

# One role shared by both Lambdas
resource "aws_iam_role" "lambda" {
  name = "askwri-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# Lets the Lambdas write logs
resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# What the Lambdas are allowed to touch
resource "aws_iam_role_policy" "lambda_access" {
  name = "askwri-lambda-access"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${local.source_bucket}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.sections.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.sections.arn
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = aws_dynamodb_table.documents.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.section.arn
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = [aws_sqs_queue.pdf.arn, aws_sqs_queue.section.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["s3vectors:PutVectors", "s3vectors:ListVectors", "s3vectors:DeleteVectors"]
        Resource = aws_s3vectors_index.chunks.index_arn
      },
    ]
  })
}

# Zip each handler file
data "archive_file" "sections" {
  type        = "zip"
  output_path = "${path.module}/sections_handler.zip"

  source {
    content  = file("${path.module}/../lambdas/sections_handler.py")
    filename = "sections_handler.py"
  }

  source {
    content  = file("${path.module}/../lambdas/labels.py")
    filename = "labels.py"
  }
}

data "archive_file" "embed" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/embed_handler.py"
  output_path = "${path.module}/embed_handler.zip"
}

# Lambda 1: PDF -> section text files
resource "aws_lambda_function" "sections" {
  function_name    = "askwri-sections"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "sections_handler.handler"
  filename         = data.archive_file.sections.output_path
  source_code_hash = data.archive_file.sections.output_base64sha256
  timeout          = 900
  memory_size      = 512

  environment {
    variables = {
      SECTIONS_BUCKET   = aws_s3_bucket.sections.bucket
      SECTION_QUEUE_URL = aws_sqs_queue.section.url
    }
  }
}

# Lambda 2: section text file -> embeddings
resource "aws_lambda_function" "embed" {
  function_name    = "askwri-embed"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "embed_handler.handler"
  filename         = data.archive_file.embed.output_path
  source_code_hash = data.archive_file.embed.output_base64sha256
  timeout          = 120
  memory_size      = 512

  environment {
    variables = {
      SECTIONS_BUCKET = aws_s3_bucket.sections.bucket
    }
  }
}

# SQS triggers: one message at a time
resource "aws_lambda_event_source_mapping" "pdf" {
  event_source_arn = aws_sqs_queue.pdf.arn
  function_name    = aws_lambda_function.sections.arn
  batch_size       = 1
}

resource "aws_lambda_event_source_mapping" "section" {
  event_source_arn = aws_sqs_queue.section.arn
  function_name    = aws_lambda_function.embed.arn
  batch_size       = 1
}

# Data storage: documents table, vector index, section text files, and the two queues.

# Documents table
resource "aws_dynamodb_table" "documents" {
  name         = "askwri-documents"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "doc_id"

  attribute {
    name = "doc_id"
    type = "S"
  }
}

# Vector bucket
resource "aws_s3vectors_vector_bucket" "vectors" {
  vector_bucket_name = "askwri-vectors"
}

# Vector index
resource "aws_s3vectors_index" "chunks" {
  vector_bucket_name = aws_s3vectors_vector_bucket.vectors.vector_bucket_name
  index_name         = "askwri-index"
  data_type          = "float32"
  dimension          = 1024
  distance_metric    = "cosine"

  metadata_configuration {
    non_filterable_metadata_keys = ["chunk_text", "title", "source_url"]
  }
}

# Bucket that holds one text file per section
resource "aws_s3_bucket" "sections" {
  bucket = local.sections_bucket
}

# Queue 1: one message per PDF to convert
resource "aws_sqs_queue" "pdf" {
  name                       = "askwri-pdf-queue"
  visibility_timeout_seconds = 960 # longer than the sections Lambda timeout
  message_retention_seconds  = 3600
}

# Queue 2: one message per section to embed
resource "aws_sqs_queue" "section" {
  name                       = "askwri-section-queue"
  visibility_timeout_seconds = 300 # longer than the embed Lambda timeout
  message_retention_seconds  = 3600
}

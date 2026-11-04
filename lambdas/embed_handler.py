"""Lambda 2. Reads one section text file from S3, cuts it into chunks, embeds each chunk
with Titan, and stores the vectors in the S3 Vectors index.
"""
import json
import os
import urllib.parse

import boto3

DOCS_TABLE = "askwri-documents"
VECTOR_BUCKET = "askwri-vectors"
VECTOR_INDEX = "askwri-index"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
SECTIONS_BUCKET = os.environ["SECTIONS_BUCKET"]

CHUNK_SIZE = 2000   # characters (about 500 tokens)
OVERLAP = 200
UPLOAD_BATCH = 500

s3 = boto3.client("s3")
brt = boto3.client("bedrock-runtime")
s3v = boto3.client("s3vectors")
docs_table = boto3.resource("dynamodb").Table(DOCS_TABLE)


def chunk_text(text):
    """Split text into ~2000-character chunks with 200 characters of overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        # Move the end back to whitespace so words stay whole (unless at the very end)
        if end < len(text):
            while end > start + OVERLAP and not text[end].isspace():
                end -= 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - OVERLAP
    return chunks


def embed(chunk):
    """Return the Titan embedding vector for a piece of text."""
    body = json.dumps({"inputText": chunk, "dimensions": 1024, "normalize": True})
    resp = brt.invoke_model(modelId=EMBED_MODEL, body=body)
    return json.loads(resp["body"].read())["embedding"]


def handler(event, context):
    message = json.loads(event["Records"][0]["body"])
    doc_id, section_id = message["doc_id"], message["section_id"]

    # 1. Read the document row and the section text
    doc = docs_table.get_item(Key={"doc_id": doc_id})["Item"]
    obj = s3.get_object(Bucket=SECTIONS_BUCKET, Key=f"sections/{doc_id}/{section_id}.txt")
    text = obj["Body"].read().decode("utf-8")
    # The section name is stored (URL-encoded) in the file's S3 metadata; keep it short
    section_title = urllib.parse.unquote(obj["Metadata"]["title"])[:200]

    # 2. Chunk and embed, building one vector record per chunk
    vectors = []
    for chunk_no, chunk in enumerate(chunk_text(text)):
        metadata = {"doc_id": doc_id, "section_id": section_id, "section_title": section_title,
                    "chunk_id": chunk_no,
                    "year": str(doc["year"]), "resource_type": "research",
                    "chunk_text": chunk, "title": doc.get("title", ""),
                    "source_url": doc.get("source_url", "")}
        if doc.get("regions"):
            metadata["regions"] = list(doc["regions"])
        if doc.get("topics"):
            metadata["topics"] = list(doc["topics"])
        if doc.get("tags"):
            metadata["tags"] = list(doc["tags"])
        vectors.append({"key": f"{doc_id}#{section_id}#{chunk_no:03d}",
                        "data": {"float32": embed(chunk)}, "metadata": metadata})

    # 3. Upload in batches of at most 500
    for n in range(0, len(vectors), UPLOAD_BATCH):
        s3v.put_vectors(vectorBucketName=VECTOR_BUCKET, indexName=VECTOR_INDEX,
                        vectors=vectors[n:n + UPLOAD_BATCH])
    print(f"{doc_id} {section_id}: {len(vectors)} chunks")

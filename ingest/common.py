"""Shared settings and AWS clients for the ingest script.
Has get_doc_keys(), which says which PDFs to process.
"""
import os

import boto3
from botocore.config import Config

# ---- Constants ----
SOURCE_BUCKET = "wri-bucket-6157-5871-0841"
PDF_QUEUE = "askwri-pdf-queue"
REGION = "us-east-1"

# Path to the list of PDFs, one folder above this file
DOCS_FILE = os.path.join(os.path.dirname(__file__), "..", "docs_to_ingest.txt")

# ---- AWS session and clients ----
# No profile is named here: boto3 uses the profile in your AWS_PROFILE environment variable
# (or your default profile).
session = boto3.Session(region_name=REGION)
BOTO_CONFIG = Config(read_timeout=600, retries={"max_attempts": 10, "mode": "adaptive"})

s3 = session.client("s3", config=BOTO_CONFIG)
sqs = session.client("sqs", config=BOTO_CONFIG)


def get_doc_keys():
    """Return the S3 keys to process: the ones in docs_to_ingest.txt, or all PDFs."""
    # 1. Read the list file, skipping blank lines and # comments
    keys = []
    with open(DOCS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                keys.append(line)
    if keys:
        return keys

    # 2. The list is empty, so list every PDF in the bucket
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=SOURCE_BUCKET):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith(".pdf"):
                keys.append(obj["Key"])
    return keys

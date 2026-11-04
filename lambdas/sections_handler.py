"""Lambda 1. Gets a PDF from S3, asks Claude Haiku to split it into English sections,
saves each section as a text file in S3, has Claude pick tags/regions/topics from fixed lists,
and queues one message per section for embedding. Re-running a document replaces everything.
"""
import json
import os
import re
import urllib.parse

import boto3
from botocore.config import Config

from labels import LANGUAGES, REGIONS, TAGS, TOPICS

SOURCE_BUCKET = "askwri-corpus-920373005453"
MANIFEST_KEY = "manifest.json"
DOCS_TABLE = "askwri-documents"
VECTOR_BUCKET = "askwri-vectors"
VECTOR_INDEX = "askwri-index"
EXTRACT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # Haiku 5.5 not subscribed in this sandbox
SECTIONS_BUCKET = os.environ["SECTIONS_BUCKET"]
SECTION_QUEUE_URL = os.environ["SECTION_QUEUE_URL"]

PROMPT = """Split this PDF into the document's logical sections, using its headings.
For each section, return its heading and the FULL text of that section translated into English
(if it is already English, copy it as-is). Leave out page headers, footers and page numbers.
Leave out tables and figures completely.
Reply with ONLY this JSON and nothing else:
{"document_title": "...", "original_language": "en", "sections": [
  {"title": "...", "page_start": 1, "page_end": 2, "text": "..."}]}"""

METADATA_PROMPT = ("Read this document and call save_metadata. Choose only the MOST relevant values, "
                   "using only the allowed values: at most 8 tags, at most 3 topics, and at most 3 "
                   "regions. Include a region only if the document is substantially about it; use an "
                   "empty list if it is not about a specific region. Do not repeat a value. Also give the language "
                   "the document itself is written in (its main language).")

# The tool Claude must call. The "enum" lists lock the answer down to our allowed values.
TOOL_CONFIG = {
    "tools": [{"toolSpec": {
        "name": "save_metadata",
        "description": "Save the tags, regions, topics and language that apply to this document.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string", "enum": TAGS}},
                "regions": {"type": "array", "items": {"type": "string", "enum": REGIONS}},
                "topics": {"type": "array", "items": {"type": "string", "enum": TOPICS}},
                "language": {"type": "string", "enum": list(LANGUAGES)},
            },
            "required": ["tags", "regions", "topics", "language"],
        }},
    }}],
    "toolChoice": {"tool": {"name": "save_metadata"}},  # force the model to call it
}

config = Config(read_timeout=600, retries={"max_attempts": 10, "mode": "adaptive"})
s3 = boto3.client("s3")
brt = boto3.client("bedrock-runtime", config=config)
sqs = boto3.client("sqs")
s3v = boto3.client("s3vectors")
docs_table = boto3.resource("dynamodb").Table(DOCS_TABLE)


def manifest_lookup(s3_key):
    """Return {year, source_url, language} for this PDF from the corpus manifest, if present.
    The real publication year matters for coverage-by-year analysis; the S3 folder prefix does not."""
    try:
        raw = s3.get_object(Bucket=SOURCE_BUCKET, Key=MANIFEST_KEY)["Body"].read()
        for rec in json.loads(raw):
            if rec.get("file") and s3_key.endswith(rec["file"]):
                date = rec.get("publication_date") or ""
                return {"year": date[:4] if date else "",
                        "source_url": rec.get("source_url", ""),
                        "language": rec.get("language", "")}
    except Exception as e:
        print("manifest lookup failed:", e)
    return {}


def make_doc_id(s3_key):
    """Turn an S3 key into a short id (same logic as ingest/common.py)."""
    name = s3_key.split("/")[-1]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    name = re.sub(r"[ _]", "-", name.lower())
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def ask_claude(pdf_bytes):
    """Send the whole PDF to Claude and return the parsed JSON. Retries once if the JSON is bad."""
    for attempt in range(2):
        resp = brt.converse(
            modelId=EXTRACT_MODEL,
            messages=[{"role": "user", "content": [
                {"document": {"format": "pdf", "name": "document", "source": {"bytes": pdf_bytes}}},
                {"text": PROMPT},
            ]}],
            inferenceConfig={"maxTokens": 32000},
        )
        text = "".join(b.get("text", "") for b in resp["output"]["message"]["content"]).strip()
        # Remove code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print("Bad JSON from the model" + (", retrying" if attempt == 0 else ""))
    raise ValueError("Model returned bad JSON twice")


def get_metadata(pdf_bytes):
    """Ask Claude (via the locked-down tool) for the document's tags, regions and topics."""
    resp = brt.converse(
        modelId=EXTRACT_MODEL,
        messages=[{"role": "user", "content": [
            {"document": {"format": "pdf", "name": "document", "source": {"bytes": pdf_bytes}}},
            {"text": METADATA_PROMPT},
        ]}],
        toolConfig=TOOL_CONFIG,
    )
    # Find the tool call in the response and read what the model put in it
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block:
            chosen = block["toolUse"]["input"]
            # Safety net: drop anything not in our allowed lists, and remove repeats
            language = chosen.get("language") if chosen.get("language") in LANGUAGES else "other"
            return (list(dict.fromkeys(t for t in chosen.get("tags", []) if t in TAGS)),
                    list(dict.fromkeys(r for r in chosen.get("regions", []) if r in REGIONS)),
                    list(dict.fromkeys(t for t in chosen.get("topics", []) if t in TOPICS)),
                    language)
    raise ValueError("Model did not call save_metadata")


def delete_old_vectors(doc_id):
    """Delete every vector of this document. The index can't search by key prefix, so list all keys."""
    old_keys = []
    pages = s3v.get_paginator("list_vectors").paginate(vectorBucketName=VECTOR_BUCKET,
                                                       indexName=VECTOR_INDEX)
    for page in pages:
        old_keys += [v["key"] for v in page["vectors"] if v["key"].startswith(doc_id + "#")]
    for n in range(0, len(old_keys), 500):  # delete_vectors accepts at most 500 keys
        s3v.delete_vectors(vectorBucketName=VECTOR_BUCKET, indexName=VECTOR_INDEX,
                           keys=old_keys[n:n + 500])
    return len(old_keys)


def handler(event, context):
    s3_key = json.loads(event["Records"][0]["body"])["s3_key"]
    doc_id = make_doc_id(s3_key)

    # 1. Download the PDF, then get the sections and the tags/regions/topics from Claude.
    #    Both calls happen BEFORE we touch any stored data, so a failure leaves the old data intact.
    pdf_bytes = s3.get_object(Bucket=SOURCE_BUCKET, Key=s3_key)["Body"].read()
    data = ask_claude(pdf_bytes)
    sections = data["sections"]
    tags, regions, topics, language = get_metadata(pdf_bytes)

    # 2. If this document was ingested before, delete its old vectors
    #    (the document row is replaced in step 5; a human-written source_url is kept)
    meta = manifest_lookup(s3_key)
    old_row = docs_table.get_item(Key={"doc_id": doc_id}).get("Item")
    # Prefer a human-entered source_url on re-ingest; otherwise seed it from the manifest.
    source_url = (old_row or {}).get("source_url") or meta.get("source_url", "")
    if old_row:
        print(f"{doc_id}: re-ingesting, deleted {delete_old_vectors(doc_id)} old vectors")

    # 3. Delete old section files for this document, so re-runs leave nothing stale
    old = s3.list_objects_v2(Bucket=SECTIONS_BUCKET, Prefix=f"sections/{doc_id}/")
    for obj in old.get("Contents", []):
        s3.delete_object(Bucket=SECTIONS_BUCKET, Key=obj["Key"])

    # 4. Save one text file per section (S3 metadata must be ASCII, so quote the title)
    section_ids = []
    section_list = []  # saved on the document row (section names and pages)
    for n, section in enumerate(sections, 1):
        section_id = f"s{n:03d}"
        s3.put_object(
            Bucket=SECTIONS_BUCKET, Key=f"sections/{doc_id}/{section_id}.txt",
            Body=section["text"].encode("utf-8"),
            Metadata={"title": urllib.parse.quote(section["title"]),
                      "page_start": str(section["page_start"]),
                      "page_end": str(section["page_end"])},
        )
        section_ids.append(section_id)
        section_list.append({"section_id": section_id, "title": section["title"],
                             "page_start": section["page_start"], "page_end": section["page_end"]})

    # 5. Write a brand-new document row (replaces any old one completely).
    #    This happens before queueing, because the embed Lambda reads the row.
    docs_table.put_item(Item={
        "doc_id": doc_id, "s3_key": s3_key,
        "year": meta.get("year") or s3_key.split("/")[0][:4],
        "resource_type": "research", "source_url": source_url,
        "source_bucket": SOURCE_BUCKET, "language": language,
        "title": data.get("document_title") or s3_key.split("/")[-1],
        "original_language": data.get("original_language", ""),
        "tags": tags, "regions": regions, "topics": topics, "sections": section_list})

    # 6. Queue one message per section so the embed Lambda picks them up
    for section_id in section_ids:
        sqs.send_message(QueueUrl=SECTION_QUEUE_URL,
                         MessageBody=json.dumps({"doc_id": doc_id, "section_id": section_id}))
    print(f"{doc_id}: {len(section_ids)} sections, language {language}, {len(tags)} tags")

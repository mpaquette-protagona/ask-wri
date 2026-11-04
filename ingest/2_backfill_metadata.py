"""Adds Type of Resource, Subtype of Resource and the page count to each document row in
DynamoDB, from doc_metadata.json (keyed by S3 key). Safe to run again.
"""
import json
import os
import re

import common

TABLE = "askwri-documents"
META_FILE = os.path.join(os.path.dirname(__file__), "doc_metadata.json")


def make_doc_id(s3_key):
    """Same rule as the sections Lambda."""
    name = s3_key.split("/")[-1]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return re.sub(r"-+", "-", re.sub(r"[ _]", "-", name.lower())).strip("-")


table = common.session.resource("dynamodb").Table(TABLE)
metadata = json.load(open(META_FILE))

for s3_key, meta in metadata.items():
    table.update_item(
        Key={"doc_id": make_doc_id(s3_key)},
        UpdateExpression="SET resource_type = :t, #st = :s, subtype_label = :l, pages_total = :p",
        ExpressionAttributeNames={"#st": "subtype"},  # "subtype" is a DynamoDB reserved word
        ConditionExpression="attribute_exists(doc_id)",  # never create a half-empty row
        ExpressionAttributeValues={":t": meta["resource_type"], ":s": meta["subtype"],
                                   ":l": meta["subtype_label"], ":p": meta["pages_total"]},
    )
print(f"Updated {len(metadata)} documents.")

"""Starts ingestion: sends one SQS message per PDF. The AWS Lambdas then convert each PDF
into sections and embed them in the background.
"""
import json

import common

# 1. Find the queue
queue_url = common.sqs.get_queue_url(QueueName=common.PDF_QUEUE)["QueueUrl"]

# 2. Send one message per PDF
keys = common.get_doc_keys()
for i, key in enumerate(keys, 1):
    common.sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps({"s3_key": key}))
    print(f"[{i}/{len(keys)}] queued {key}")

print("Done. The Lambdas are now working in the background.")
print("Watch progress in the CloudWatch logs of askwri-sections and askwri-embed.")

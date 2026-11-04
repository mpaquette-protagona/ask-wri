# AskWRI: Implementation Spec

You are implementing this project in this repository. Read this whole file before writing any code, then build it in the order given in section 10. The reference documents [AskWRI-vision-document.md](AskWRI-vision-document.md) and [AskWRI-technical-document.md](AskWRI-technical-document.md) give background. **This spec overrides them** wherever they differ.

## 0. What we're building

A chatbot that answers questions using World Resources Institute (WRI) research PDFs stored in S3. Every answer cites its source document (title, link, pages, quoted passage). If the documents don't contain the answer, the chatbot says so instead of guessing. It can also write a research briefing on a topic and point out gaps in WRI's coverage.

This is a hackathon build with a few hours available. The user will walk inexperienced students through the code afterwards, so **simple, readable code is a hard requirement**. Simplicity must not cost any functionality in this spec.

---

## 1. Rules for how you write the code

1. **Build exactly what this spec lists.** No tests, no evaluation scripts, no docs other than the one `README.md` (section 12), no CLI flags, no logging setup, no config classes, no Docker files, and no features that aren't listed here. Section 11 lists what's out of scope.
2. **Plain Python 3.12 scripts.** Top-level functions and a simple `main()`. No classes (except where a library requires one), no dataclasses, no async, no abstract helpers or "utils" layers. Use type hints only where Strands needs them (tool function signatures).
3. **Files stay short and readable.** Aim for under ~150 lines per file. Start every Python file with a 2–4 line docstring saying what it does in plain English. Add a short comment above each logical step (e.g. `# 2. Ask Claude to split the PDF`). Write comments for a beginner. Terraform files get a one-line `#` comment at the top and a short comment above each resource.
4. **Constants go at the top of each file in UPPER_CASE.** Bucket names, table names, model IDs, region. No `.env` files and no secrets in code.
5. **Use `print()` for progress**, e.g. `print(f"[3/10] {doc_id}: 14 sections")`.
6. **Minimal error handling.** Only where this spec asks for it (the JSON retry in 5.3). Otherwise let errors surface. In Lambdas, an uncaught error makes SQS retry the message, which is the intended behavior.
7. **Dependencies:** only `boto3`, `requests`, `streamlit`, `strands-agents`, `bedrock-agentcore`, `bedrock-agentcore-starter-toolkit`. The Lambdas use only `boto3`, which the Lambda runtime already provides, so they need no packaging of dependencies.
8. **AWS access from Python goes through boto3 only.** The installed AWS CLI (v1) is too old for S3 Vectors. Don't use it for anything except what section 9 explicitly says.
9. **All infrastructure is Terraform** (section 5.1), except the AgentCore runtime, which the `agentcore` CLI deploys (section 9). Don't create AWS resources from Python scripts.

---

## 2. Environment facts (already verified)

| Item | Value |
|---|---|
| OS / shell | Windows 11, PowerShell. Python 3.12.10, boto3 1.40.45+ (supports `s3vectors` and `bedrock-agentcore`). Terraform 1.14.6 |
| AWS profile | `builder`. It has **no default region**, so always pass `us-east-1` |
| Region | `us-east-1` |
| Account | `615758710841` |
| Source bucket | `wri-bucket-6157-5871-0841`. It currently contains only `2024_publications/` (330 PDFs). Later folders like `2025_publications/` may appear and must be handled the same way |
| Chat model | `us.anthropic.claude-sonnet-5-5` (cross-region inference profile, confirmed available) |
| PDF→sections model | `us.anthropic.claude-haiku-5-5` (confirmed available) |
| Embedding model | `amazon.titan-embed-text-v2:0`, 1024 dimensions, `normalize: true` |
| PDF size | Every PDF is small enough to send to the model in one call (under Bedrock's 4.5 MB document limit). Do not split PDFs into batches |

Local scripts create the boto3 session like this:

```python
from botocore.config import Config
session = boto3.Session(profile_name="builder", region_name="us-east-1")
BOTO_CONFIG = Config(read_timeout=600, retries={"max_attempts": 10, "mode": "adaptive"})
```

The long `read_timeout` is required for long Bedrock calls (the sections Lambda creates its client the same way, without a profile).

**Exceptions:** `agent/agent.py` and the Lambdas run with an IAM role, so they use `boto3.Session(region_name="us-east-1")` / plain `boto3.client(...)` with **no profile name**. When you run `agent/agent.py` locally, set `$env:AWS_PROFILE="builder"` first.

---

## 3. Architecture

```
INGESTION
  local:
   └─ ingest/1_start_ingestion.py one SQS message per PDF → askwri-pdf-queue

  in AWS (triggered by SQS):
   askwri-pdf-queue → Lambda askwri-sections   (Claude Haiku reads the whole PDF, returns English sections)
        ├─ writes one text file per section → S3 askwri-sections-<account>/sections/<doc_id>/<section_id>.txt
        ├─ asks Claude (forced tool call, fixed option lists) for tags, regions, topics
        ├─ writes the document row (title, language, tags, regions, topics, ...) → DynamoDB askwri-documents
        └─ sends one SQS message per section → askwri-section-queue
   askwri-section-queue → Lambda askwri-embed  (2,000-char chunks → Titan embeddings)
        └─ S3 Vectors askwri-vectors/askwri-index

CHAT
  app/streamlit_app.py → AgentCore Runtime → agent/agent.py
      orchestrator (Strands Agent)
        ├─ research_agent tool (Q&A + briefings)   uses search_wri
        └─ gaps_agent tool (coverage + gaps)       uses search_wri, list_documents
      search_wri: vector search on chunks → group hits by (doc_id, section_id)
                  → return the FULL section text file from S3
```

**Key idea:** chunks are for *finding* the right spot. Answers are written from *whole sections*. Each section is one text file in S3, so turning a chunk hit into its section is one `get_object` by `sections/<doc_id>/<section_id>.txt`.

---

## 4. Repository layout (create exactly this)

```
breaking_barriers/
├── SPEC.md                    (this file, already exists)
├── README.md                  what the project does and how to run it (section 12)
├── requirements.txt           all 6 dependencies from rule 7
├── docs_to_ingest.txt         list of PDFs to ingest (see 5.0)
├── terraform/
│   ├── terraform.tfvars       sets agent_role_name for this account
│   ├── main.tf                provider, variables, account lookup
│   ├── storage.tf             DynamoDB table, S3 vectors, sections bucket, queues
│   ├── lambdas.tf             IAM role, the two Lambdas, SQS triggers
│   └── agent_access.tf        inline policy for the AgentCore execution role
├── lambdas/
│   ├── labels.py              the allowed TAGS, REGIONS and TOPICS lists (5.3)
│   ├── sections_handler.py    PDF → section text files → metadata → section messages
│   └── embed_handler.py       section text file → chunks → vectors
├── ingest/
│   ├── common.py              constants + session/clients + get_doc_keys()
│   └── 1_start_ingestion.py
├── agent/
│   ├── agent.py               does not import from ingest/ (only from labels.py)
│   ├── labels.py              exact copy of lambdas/labels.py (keep identical)
│   └── requirements.txt       strands-agents, bedrock-agentcore, boto3
└── app/
    └── streamlit_app.py
```

The ingest scripts are run as `python ingest/1_start_ingestion.py`. That puts `ingest/` on the import path, so they use `import common`.

**Resource names** (constants in `ingest/common.py`, `agent/agent.py` and the Lambdas, and the same names in Terraform):
`DOCS_TABLE = "askwri-documents"`, `VECTOR_BUCKET = "askwri-vectors"`, `VECTOR_INDEX = "askwri-index"`, `SECTIONS_BUCKET = "askwri-sections-615758710841"`, `PDF_QUEUE = "askwri-pdf-queue"`, `SECTION_QUEUE = "askwri-section-queue"`.

(The old `askwri-sections` DynamoDB table is no longer used. Leave it alone; do not delete it and do not manage it in Terraform.)

---

## 5. Ingestion

### 5.0 `ingest/common.py` and `docs_to_ingest.txt`

- Constants: the source bucket, `PDF_QUEUE`, the region, and the profile.
- `session`, `BOTO_CONFIG`, and clients: `s3` and `sqs`.
- `get_doc_keys()`:
  - Read `docs_to_ingest.txt` from the repo root (path relative to this file). Ignore blank lines and lines starting with `#`.
  - If any keys remain, return them.
  - Otherwise list every key ending in `.pdf` (case-insensitive) in the source bucket, using a paginator, and return them all.

`make_doc_id(s3_key)` and the year are needed only in `lambdas/sections_handler.py`:
- `make_doc_id(s3_key)`: take the filename without `.pdf`, lowercase it, replace spaces and `_` with `-`, collapse repeated `-`, and strip leading/trailing `-`.
  Example: `2024_publications/24_WP_Climate Action Matrilineal Systems v5.pdf` → `24-wp-climate-action-matrilineal-systems-v5`.
- year: the first 4 characters of the key's folder name (`2024_publications` → `"2024"`).

`docs_to_ingest.txt` starts with this header comment, followed by the chosen keys (none means ALL PDFs):
```
# One S3 key per line, e.g. 2024_publications/2024-methane-briefing-EN.pdf
# If no keys are listed, ALL PDFs in the bucket are ingested.
```

### 5.1 Terraform (`terraform/`)

Use the AWS provider (`hashicorp/aws`, latest 6.x, which includes the `aws_s3vectors_*` resources) and `hashicorp/archive`. Provider: `region = "us-east-1"`, `profile = "builder"`. Variable `agent_role_name`: the name of the role the AgentCore deploy created. Its default is `""`, and the `askwri-data-access` policy below is created only when it is non-empty (`count`), because that role exists only after the agent is deployed. A `terraform.tfvars` file sets it for this account (`AmazonBedrockAgentCoreSDKRuntime-us-east-1-a28949e873`). A `moved` block keeps the policy's old address, so it is not replaced.

Resources:

| Resource | Details |
|---|---|
| DynamoDB `askwri-documents` | partition key `doc_id` (S), `PAY_PER_REQUEST` |
| S3 vector bucket `askwri-vectors` and index `askwri-index` | `float32`, dimension 1024, `cosine`, `non_filterable_metadata_keys = ["chunk_text", "title", "source_url"]` |
| S3 bucket `askwri-sections-<account>` | holds the section text files. Bucket name is built from `data.aws_caller_identity` |
| SQS `askwri-pdf-queue` | `visibility_timeout_seconds = 960`, `message_retention_seconds = 3600` |
| SQS `askwri-section-queue` | `visibility_timeout_seconds = 300`, `message_retention_seconds = 3600` |
| Lambda `askwri-sections` | python3.12, handler `sections_handler.handler`, timeout 900, memory 512. Env: `SECTIONS_BUCKET`, `SECTION_QUEUE_URL`. Triggered by `askwri-pdf-queue` with `batch_size = 1` |
| Lambda `askwri-embed` | python3.12, handler `embed_handler.handler`, timeout 120, memory 512. Triggered by `askwri-section-queue` with `batch_size = 1` |
| IAM role for both Lambdas | basic logging; S3 get/put/delete/list on the sections bucket and get on the source bucket; `bedrock:InvokeModel` (resource `*`); DynamoDB get/put on `askwri-documents`; `sqs:SendMessage` to the section queue; receive/delete/get-attributes on both queues; `s3vectors:PutVectors`, `ListVectors` and `DeleteVectors` on the index |
| Inline policy `askwri-data-access` on the existing AgentCore execution role | `s3vectors:QueryVectors` and `GetVectors` on the index; `dynamodb:GetItem` and `Scan` on `askwri-documents`; `s3:GetObject` on the sections bucket; `bedrock:InvokeModel` on `arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0` |

Package each Lambda with `data "archive_file"`: the embed Lambda zips only `embed_handler.py`; the sections Lambda zips `sections_handler.py` and `labels.py` (use two `source` blocks).

**Existing resources:** in the original AWS account the documents table and the vector bucket and index were created before Terraform was added, so they were adopted once with `import` blocks. Those blocks have been **removed** (they fail in a clean account, and the state already tracks the resources). The Terraform code must work on a clean account. `terraform plan` must never show a destroy or replacement of an existing resource; if it does, stop and ask.

### 5.2 Document metadata (tags, regions, topics)

There is **no wri.org scraping**. Claude assigns the metadata in `lambdas/sections_handler.py` (step 6 of 5.3). The allowed values live in `lambdas/labels.py` as three lists of exact strings:

- `TAGS`: the full tag list the user supplied (about 170 values, e.g. `adaptation`, `carbon pricing`, `energy efficiency`, `NDC`, `Top Outcome: 2024`). Copy them exactly, including capitalization.
- `REGIONS`: `Africa`, `Asia`, `Europe`, `Latin America`, `North America`, `Oceania`.
- `TOPICS`: `Business`, `Cities`, `Climate`, `Economics`, `Energy`, `Equity & Governance`, `Finance`, `Food`, `Forests`, `Freshwater`, `Ocean`.

A document can have several tags, regions and topics (or none). The `askwri-documents` row fields are:

| Field | Value |
|---|---|
| `doc_id` | from `make_doc_id` |
| `s3_key` | full S3 key |
| `year` | e.g. `"2024"` (first 4 characters of the key's folder name) |
| `resource_type` | always `"research"` |
| `title`, `original_language` | from the sections call |
| `tags`, `regions`, `topics` | lists of strings from the allowed lists (can be empty) |
| `sections` | list of `{section_id, title, page_start, page_end}`, one per section file |
| `source_url` | `""` unless a human has filled it in. Never overwrite an existing value (use `if_not_exists`) |

### 5.3 `lambdas/sections_handler.py`: PDF → section text files

Triggered by `askwri-pdf-queue`. Each message body is JSON: `{"s3_key": "2024_publications/x.pdf"}`. Handle `event["Records"][0]` (batch size is 1).

1. Download the PDF bytes from the source bucket (constant `SOURCE_BUCKET`).
2. Call Claude once, with the **whole PDF**, via Converse:
   ```python
   resp = brt.converse(
       modelId=EXTRACT_MODEL,  # us.anthropic.claude-haiku-5-5
       messages=[{"role": "user", "content": [
           {"document": {"format": "pdf", "name": "document", "source": {"bytes": pdf_bytes}}},
           {"text": PROMPT},
       ]}],
       inferenceConfig={"maxTokens": 32000},
   )
   text = "".join(block.get("text", "") for block in resp["output"]["message"]["content"])
   ```
   Join all blocks as shown, because the response may start with a reasoning block that has no `text`.
3. Use this prompt verbatim:
   ```
   Split this PDF into the document's logical sections, using its headings.
   For each section, return its heading and the FULL text of that section translated into English
   (if it is already English, copy it as-is). Leave out page headers, footers and page numbers.
   Leave out tables and figures completely.
   Reply with ONLY this JSON and nothing else:
   {"document_title": "...", "original_language": "en", "sections": [
     {"title": "...", "page_start": 1, "page_end": 2, "text": "..."}]}
   ```
4. **Parse:** strip any code fences, then `json.loads`. If that fails, call the model again once. If it fails again, raise an error (SQS will retry the message).
5. **Classify the document** with a second Converse call on the same PDF. The model must answer through a tool, and the tool's schema restricts every value to the allowed lists in `labels.py`:
   ```python
   TOOL_CONFIG = {
       "tools": [{"toolSpec": {
           "name": "save_metadata",
           "description": "Save the tags, regions and topics that apply to this document.",
           "inputSchema": {"json": {
               "type": "object",
               "properties": {
                   "tags":    {"type": "array", "items": {"type": "string", "enum": TAGS}},
                   "regions": {"type": "array", "items": {"type": "string", "enum": REGIONS}},
                   "topics":  {"type": "array", "items": {"type": "string", "enum": TOPICS}},
               },
               "required": ["tags", "regions", "topics"],
           }},
       }}],
       "toolChoice": {"tool": {"name": "save_metadata"}},   # force the model to call it
   }
   ```
   Prompt (verbatim): `Read this document and call save_metadata. Choose only the MOST relevant values, using only the allowed values: at most 8 tags, at most 3 topics, and at most 3 regions. Include a region only if the document is substantially about it; use an empty list if it is not about a specific region. Do not repeat a value.`
   Take the `input` of the `toolUse` content block in the response. As a safety net, drop any value not in the allowed lists and remove repeats while keeping order (`list(dict.fromkeys(t for t in values if t in TAGS))`).
6. **Replace any earlier ingestion of this document.** Do this only after steps 2 and 5 succeeded, so a failed run leaves the old data untouched. Re-ingesting a document replaces **everything** about it:
   - Read the existing `askwri-documents` row. If one exists, remember its `source_url` (a human may have filled it in; everything else is replaced), then delete all of the document's vectors: S3 Vectors cannot search by key prefix, so list every key in the index with the `list_vectors` paginator, keep the keys that start with `<doc_id>#`, and call `delete_vectors` in batches of at most 500 keys. A first-time ingestion has no row, so it skips this scan.
   - Delete all objects under `sections/<doc_id>/` in the sections bucket.
7. **Write the section files.** `put_object` one file per section at key `sections/<doc_id>/<section_id>.txt` (`section_id` is `"s001"`, `"s002"`, …), body = the section text (UTF-8), with S3 object metadata `title`, `page_start`, `page_end`. S3 metadata must be ASCII, so store the title with `urllib.parse.quote(title)`.
8. **Write a brand-new `askwri-documents` row** with `put_item` (this replaces the whole old row, so no old field survives), containing the fields listed in 5.2: `title` (use the filename if no title was returned), `original_language`, `tags`, `regions`, `topics`, `sections` (the list from 5.2), `s3_key`, `year`, `resource_type`, and `source_url` (the remembered value, or `""`). This must happen **before** step 9, because the embed Lambda reads this row.
9. Send one SQS message per section to `askwri-section-queue` (URL from env `SECTION_QUEUE_URL`), body JSON `{"doc_id": ..., "section_id": ...}`.
10. Print `doc_id: N sections, language xx, K tags` (and, when re-ingesting, how many old vectors were deleted).

### 5.4 `lambdas/embed_handler.py`: section file → S3 Vectors

Triggered by `askwri-section-queue`. Each message body is JSON `{"doc_id": ..., "section_id": ...}`. Handle `event["Records"][0]`.

1. Read the document row (title, source_url, tags, regions, topics, year) from `askwri-documents`, and the section text from `sections/<doc_id>/<section_id>.txt` in the sections bucket. Also read the section name from that file's S3 object metadata `title` (decode with `urllib.parse.unquote`, cut to 200 characters) as `section_title`. It is stored in every chunk's metadata next to `title` (the document title).
2. Split the text into chunks of **2,000 characters with 200-character overlap** (≈500 tokens). Move each chunk's end back to the nearest whitespace so words stay whole. Write this as one small function, `chunk_text(text)`.
3. Embed each chunk:
   ```python
   body = json.dumps({"inputText": chunk, "dimensions": 1024, "normalize": True})
   resp = brt.invoke_model(modelId=EMBED_MODEL, body=body)
   vector = json.loads(resp["body"].read())["embedding"]
   ```
4. Build one vector record per chunk:
   ```python
   metadata = {"doc_id": doc_id, "section_id": section_id, "section_title": section_title,
               "chunk_id": chunk_no,
               "year": year, "resource_type": "research",
               "chunk_text": chunk, "title": title, "source_url": source_url}
   if regions: metadata["regions"] = list(regions)   # lists of strings; don't store empty values
   if topics: metadata["topics"] = list(topics)
   if tags: metadata["tags"] = list(tags)
   {"key": f"{doc_id}#{section_id}#{chunk_no:03d}", "data": {"float32": vector}, "metadata": metadata}
   ```
   DynamoDB returns numbers as `Decimal`. Convert them with `int()` / `str()` before putting them in metadata.
5. Upload with `s3v.put_vectors(vectorBucketName=..., indexName=..., vectors=batch)` in batches of **at most 500**. Re-running overwrites by key.
6. Print `doc_id section_id: N chunks`.

### 5.5 `ingest/1_start_ingestion.py`

For each key from `get_doc_keys()`, send one message `{"s3_key": key}` to `askwri-pdf-queue` (look up the URL with `sqs.get_queue_url`) and print `[i/N] queued <key>`. At the end print that the Lambdas are now working in the background and that progress can be watched in CloudWatch logs or the queue's message counts.

---

## 6. Agent: `agent/agent.py`

This file holds: constants, clients, 2 data tools, 2 sub-agent tools, the orchestrator, and the AgentCore entrypoint. It imports `TAGS`, `REGIONS` and `TOPICS` from `agent/labels.py`, an exact copy of `lambdas/labels.py` (both files carry a comment saying to keep them identical).

### 6.0 Limits and shared state

Constant `MAX_SEARCHES = 5`. A module-level dict `state` holds, for the current question: `searches`, `seen` (a set of `(doc_id, section_id)` already returned) and `source_no`. The search limit is **per sub-agent run**: the `research_agent` and `gaps_agent` tools each set `state["searches"] = 0` before they run their Agent, so one sub-agent can't use up the other's searches. `seen` and `source_no` last for the whole question. `reset_state()` sets them to zero/empty; call it once at import and at the start of every `invoke` (every new question). A helper `read_section(doc_id, section_id)` does the S3 read (step 5 of 6.1), adds the pair to `seen`, increments `source_no`, and returns the block, so **`[SOURCE n]` numbers are unique across every call within one question**.

### 6.1 Tool `search_wri` (semantic search and/or metadata filters)

The filter parameters use `typing.Literal` types built from the label lists, so the allowed values appear in the tool definition the model sees:

```python
Region = Literal[tuple(REGIONS)]   # likewise Topic from TOPICS, Tag from TAGS

@tool
def search_wri(query: str = "", region: Optional[Region] = None, topic: Optional[Topic] = None,
               tag: Optional[Tag] = None, document: str = "") -> str:
    """Find the most relevant full sections of WRI research documents, with citation details.
    Give a query (semantic search), and/or filters (region, topic, tag; each limits the search
    to documents with that value; document is a document id from list_documents and limits the
    search to that one document). At least one of them is required. Returns up to 5 sections
    you have not been given yet. You may call this at most 5 times per question."""
```

1. If none of `query`, `region`, `topic`, `tag`, `document` is given, return `Give a query and/or at least one filter.` If `state["searches"] >= MAX_SEARCHES`, return `RETRIEVAL_LIMIT_REACHED: no more searches allowed. Answer with what you have.` Otherwise increment `state["searches"]`.
2. Embed `query` with Titan (same call as 5.4). **If there is no query, embed the filter values joined by spaces instead** (for `document`, use the doc id with `-` replaced by spaces). S3 Vectors cannot search by filter alone.
3. Build the filter from the parts that are set:
   - region: `{"regions": {"$eq": region}}`
   - topic: `{"topics": {"$eq": topic}}`
   - tag: `{"tags": {"$eq": tag}}`
   - document: `{"doc_id": {"$eq": document}}`
   - (with S3 Vectors, `$eq` on a list field matches when any element equals the value; confirm this in step 4 of section 10)
   - two or more set: `{"$and": [ ...the filters that are set... ]}`
   - none set: pass no `filter` argument at all
4. Query:
   ```python
   hits = s3v.query_vectors(vectorBucketName=VECTOR_BUCKET, indexName=VECTOR_INDEX,
                            queryVector={"float32": vector}, topK=30,
                            returnMetadata=True, returnDistance=True, **filter_kwargs)["vectors"]
   ```
5. **Stitch to sections.** Go through `hits` in order and collect unique `(doc_id, section_id)` pairs that are **not already in `state["seen"]`**. Stop at 5.
6. For each pair, `read_section`: `s3.get_object` the file `sections/<doc_id>/<section_id>.txt` from the sections bucket (text = body, title and pages from the object `Metadata`, title decoded with `urllib.parse.unquote`), and `get_item` the document row for its title and URL. Return one block per section:
   ```
   [SOURCE <n>] Title: <title> | URL: <source_url or "no web page"> | Pages: <start>-<end> | Section: <section_title>
   <full section text>
   ```
7. If there are no hits, return exactly `NO_RESULTS`. If there are hits but every section was already returned, return `NO_NEW_RESULTS: every matching section was already returned earlier.`

### 6.2 Tool `list_documents`

```python
@tool
def list_documents(tag: Optional[Tag] = None, region: Optional[Region] = None,
                   topic: Optional[Topic] = None) -> str:
    """List the WRI documents in the library (document id, title, year, regions, topics, tags),
    optionally filtered by tag, region or topic. Use a document id with search_wri's document filter."""
```

The three parameters use the same `Literal` types as `search_wri`, so the allowed values appear in the tool definition. Scan `askwri-documents` with pagination. Keep a document only if it contains every value that was given (exact match against its `tags`, `regions` and `topics` lists). Return one line per document: `<doc_id> | <title> | <year> | <regions> | <topics> | <tags>`.

### 6.3 Agents (Strands "agents as tools")

```python
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

MODEL = BedrockModel(model_id="us.anthropic.claude-sonnet-5-5", region_name="us-east-1")

@tool
def research_agent(request: str) -> str:
    """Answer a question about WRI research, or write a research briefing, with citations."""
    return str(Agent(model=MODEL, system_prompt=RESEARCH_PROMPT, tools=[search_wri])(request))

@tool
def gaps_agent(topic: str) -> str:
    """Map what WRI has published on a topic and suggest gaps and follow-up research."""
    return str(Agent(model=MODEL, system_prompt=GAPS_PROMPT, tools=[search_wri, list_documents])(topic))

orchestrator = Agent(model=MODEL, system_prompt=ORCHESTRATOR_PROMPT, tools=[research_agent, gaps_agent])

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload):
    reset_state()  # new question: reset the call counts and the "already returned" list
    return {"answer": str(orchestrator(payload["prompt"]))}

if __name__ == "__main__":
    app.run()
```

Each AgentCore session runs in its own process, so the module-level `orchestrator` remembers the conversation within one chat session. Don't add any other memory mechanism.

### 6.4 System prompts (use verbatim as module constants)

**ORCHESTRATOR_PROMPT**
```
You are AskWRI, the front desk for World Resources Institute (WRI) research.
Send questions and briefing requests to research_agent. Send questions about coverage, gaps,
or what WRI has not yet studied to gaps_agent. Include relevant context from earlier in the
conversation in the request you pass on. Return the agent's answer to the user unchanged,
including every citation. Never answer from your own knowledge.
```

**RESEARCH_PROMPT**
```
You answer ONLY from WRI documents returned by the search_wri tool. Never use outside knowledge.
- Search before answering. Use the region or tag filter when the user names a region or topic.
- End every factual sentence with a citation like [1]. Finish with a "Sources" list, one line per
  source: [n] Title, pages X-Y, URL, then a short quoted passage that supports the claim.
- If search_wri returns NO_RESULTS, or the sections do not actually answer the question, reply
  exactly: "I couldn't find this in the WRI documents I have access to." and stop. Do not guess.
- If the user asks for a briefing, use this format: Summary (3-4 sentences), Key findings
  (bullets, each cited), Related WRI publications (titles and links), Sources.
```

**GAPS_PROMPT**
```
You map WRI's research coverage on a topic. Use search_wri and list_documents to see what WRI
has published. Reply with three parts: "What WRI has covered" (cited, using [n] citations and a
Sources list: [n] Title, pages X-Y, URL), "Where coverage is thin", and "Suggested research
directions". Start every suggestion with "Suggestion:". End with one line noting that gaps may
reflect the sample of documents loaded, not all of WRI's work.
```

---

## 7. UI: `app/streamlit_app.py`

- Constants: `AGENT_ARN = ""` (fill in after deploy, section 9) and `LOCAL_URL = "http://localhost:8080/invocations"`.
  - If `AGENT_ARN` is empty, POST to `LOCAL_URL` with `requests`.
  - Otherwise call AgentCore:
  ```python
  client = boto3.Session(profile_name="builder", region_name="us-east-1").client("bedrock-agentcore")
  resp = client.invoke_agent_runtime(agentRuntimeArn=AGENT_ARN,
                                     runtimeSessionId=st.session_state.session_id,
                                     payload=json.dumps({"prompt": user_text}))
  answer = json.loads(resp["response"].read())["answer"]
  ```
- `st.session_state.session_id = str(uuid.uuid4())` on first load. AgentCore requires at least 33 characters, and a uuid4 string has 36.
- Chat UI uses `st.title("AskWRI")`, `st.chat_input`, and `st.chat_message`, with the history in `st.session_state.messages`. Render answers with `st.markdown`. Wrap the agent call in `st.spinner("Searching WRI research...")`.

---

## 8. Running locally

```powershell
pip install -r requirements.txt
cd terraform; terraform init; terraform apply; cd ..     # creates all infrastructure and Lambdas
python ingest/1_start_ingestion.py                       # Lambdas do the rest in AWS
$env:AWS_PROFILE="builder"; python agent/agent.py       # terminal 1 (serves :8080)
streamlit run app/streamlit_app.py                      # terminal 2
```

## 9. Deploying the agent to AgentCore

1. From `agent/`, with `$env:AWS_PROFILE="builder"` and `$env:AWS_DEFAULT_REGION="us-east-1"` set, use the starter toolkit's `agentcore` CLI.
   - Run `agentcore --help` and `agentcore configure --help` first to confirm the subcommand names and whether a non-interactive flag exists.
   - Configure with entrypoint `agent.py`, its `requirements.txt`, memory disabled, an auto-created execution role, and the default CodeBuild/ECR settings.
   - Then run `agentcore deploy`.
   - **If the CLI insists on interactive prompts you can't answer, stop and ask the user to run that one command in their own terminal.**
2. The execution role's data access comes from Terraform (`agent_access.tf`, section 5.1), not from boto3. After the first deploy, put the execution role's name into `agent_role_name` (in `terraform/terraform.tfvars`) and run `terraform apply` again. Don't modify any other IAM entities.
3. Put the runtime ARN into `AGENT_ARN` in `app/streamlit_app.py`.

---

## 10. Build order and how to verify each step

Do the steps in order. Don't move on until the step's check passes. Fix problems before continuing.

| # | Build | Verify |
|---|---|---|
| 1 | `requirements.txt`, `docs_to_ingest.txt`, `terraform/`, `lambdas/`, `ingest/common.py` | `terraform init` and `terraform validate` succeed. `terraform plan` shows no destroys (existing resources are imported). `terraform apply` succeeds; running `plan` again shows no changes. |
| 2 | **Stop and ask the user** which ~10 PDFs to put in `docs_to_ingest.txt`, unless the file already lists keys the user confirmed. Include at least one non-English file. Never run ingestion with an empty list (which means ALL documents) unless the user explicitly says to. | User confirmed the list. |
| 3 | `lambdas/labels.py`, `1_start_ingestion.py` | One row per doc in `askwri-documents`, each with `tags`, `regions` and `topics` that are all inside the allowed lists. After the queues drain (poll queue message counts), section files exist in the sections bucket for each doc, and a non-English doc's section text is English. |
| 4 | Embedding (done by the `askwri-embed` Lambda) | Run a throwaway `query_vectors` call (don't save it as a file) and confirm hits come back. Also confirm the `$eq` filters work on the list fields `tags`, `regions` and `topics` using values that exist on an ingested document. If one doesn't work, switch both `search_wri` and this spec's 6.1 to `{"<field>": {"$in": [value]}}`. |
| 5 | `agent/agent.py` | Run locally and POST `{"prompt": "What has WRI published on methane?"}` to `localhost:8080/invocations` (adjust the question to the ingested docs). The answer has `[n]` citations and a Sources list. An off-topic question ("What is WRI's position on cryptocurrency?") gets the decline sentence. A gaps question returns "Suggestion:" lines. Also check: a search with only a filter works; the 5-search limit returns `RETRIEVAL_LIMIT_REACHED`; citation numbers in an answer are unique. |
| 6 | `app/streamlit_app.py` against the local agent | Run it and show the user it works (or give the user the command to open it). |
| 7 | Deploy (section 9) and switch Streamlit to `AGENT_ARN` | The same questions give equivalent answers through AgentCore. |

When finished, report to the user what was built, what was verified, and anything that didn't work. **Ask the user before ingesting the full bucket.**

---

## 11. Out of scope (do not build)

Tests and evaluation scripts · docs other than `README.md` · hybrid/BM25 keyword search · translating answers into other languages · Bedrock Guardrails · AgentCore Memory or Gateway · dead-letter queues, other triggers, or any Lambda/queue beyond the two listed · PDF splitting or batching · tables and figures · authentication · Docker files beyond what `agentcore` generates · de-duplicating EN/CN copies · retries beyond the JSON retry in 5.3 and the boto3 retry config · deleting any AWS resources (including the old `askwri-sections` table).

---

## 12. README.md

One `README.md` in the repo root, written for a beginner who has never seen the project. It must cover: what the project does; an architecture overview (the diagram from section 3 in plain words); the repository layout; prerequisites; step-by-step setup and run commands in the order of sections 8 and 9 (including the two-step `agent_role_name` Terraform apply); how to re-ingest a document (it replaces everything); example questions; how the agent's tools and limits work; the account-specific values someone else must change; known limitations; and how to tear everything down. Keep it accurate: every command in it must be one that actually works.

# AskWRI

AskWRI is a chatbot that answers questions using World Resources Institute (WRI) research PDFs.

- Every answer **cites its source**: document title, pages, link (if known) and a quoted passage.
- If the documents don't contain the answer, it says so instead of guessing.
- It can write a **research briefing** on a topic.
- It can map **where WRI's research has gaps** on a topic and suggest follow-up research.

It runs entirely on AWS (Amazon Bedrock, S3, DynamoDB, SQS, Lambda, AgentCore). The chat page is a small Streamlit app.

---

## How it works

```
INGESTION  (turns PDFs into searchable data)

  you run: python ingest/1_start_ingestion.py
     │  one SQS message per PDF
     ▼
  Lambda "askwri-sections"
     • Claude Haiku reads the whole PDF and splits it into English sections
     • Claude picks tags, regions and topics, but ONLY from fixed lists (lambdas/labels.py)
     • saves one text file per section in S3
     • saves the document's details in DynamoDB
     │  one SQS message per section
     ▼
  Lambda "askwri-embed"
     • cuts the section into ~2,000-character chunks
     • turns each chunk into a vector (Amazon Titan embeddings)
     • stores the vectors in S3 Vectors

CHAT

  Streamlit page  →  AgentCore Runtime  →  agent/agent.py
        orchestrator
          ├─ research_agent  (answers questions and writes briefings)
          └─ gaps_agent      (what is covered, where it is thin, what to research next)
```

**The key idea:** chunks are only used to *find* the right place. The agent answers from the *whole section* the chunk came from, which is stored as a text file in S3.

### What the agent can do

| Tool | What it does |
|---|---|
| `search_wri` | Finds the most relevant sections. Give a text query (semantic search) and/or filters: `region`, `topic`, `tag`, or `document` (a document id). Returns up to 5 sections per call. |
| `list_documents` | Lists the documents in the library (id, title, year, regions, topics, tags), optionally filtered by tag, region or topic. Used by the gaps agent to see what exists. |

Limits per question: each sub-agent can search at most 5 times, a section is never given to the agent twice, and citation numbers are unique. The allowed values for `region`, `topic` and `tag` are built into the tool definitions, so the agent can't invent one.

---

## What's in this repository

```
README.md                 this file
SPEC.md                   the full build specification (the source of truth)
requirements.txt          Python packages for the scripts and the Streamlit app
docs_to_ingest.txt        which PDFs to ingest (one S3 key per line; empty = ALL PDFs)
terraform/                all infrastructure as code (tables, buckets, queues, Lambdas, IAM)
lambdas/
  sections_handler.py     Lambda 1: PDF -> section text files + metadata
  embed_handler.py        Lambda 2: section -> chunks -> vectors
  labels.py               the allowed tags, regions and topics
ingest/
  common.py               settings and helper to read docs_to_ingest.txt
  1_start_ingestion.py    sends one SQS message per PDF
agent/
  agent.py                the chat agent (runs on AgentCore)
  labels.py               copy of lambdas/labels.py (keep them identical!)
  requirements.txt        packages the deployed agent needs
app/
  streamlit_app.py        the chat page
```

---

## Before you start

You need:

- **Python 3.12** and `pip`
- **Terraform** (1.5 or newer)
- An **AWS account** with permission to create the resources above, and an AWS CLI/SDK profile named **`builder`** (`aws configure --profile builder`). The region used everywhere is **`us-east-1`**.
- **Amazon Bedrock model access** in `us-east-1` for: Claude Sonnet 5.5 (`us.anthropic.claude-sonnet-5-5`), Claude Haiku 5.5 (`us.anthropic.claude-haiku-5-5`) and Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`).
- The WRI PDFs in an S3 bucket you can read (this project uses `wri-bucket-6157-5871-0841`, folder `2024_publications/`).

Commands below are for **PowerShell** on Windows.

---

## Set it up and run it

### 1. Install the Python packages

```powershell
pip install -r requirements.txt
```

### 2. Create the AWS infrastructure

```powershell
cd terraform
terraform init
terraform apply        # type "yes" when asked
cd ..
```

This creates the DynamoDB table, the vector index, the sections bucket, the two queues and the two Lambdas. (Leave `agent_role_name` empty for now. See step 6.)

### 3. Choose which PDFs to ingest

Open [docs_to_ingest.txt](docs_to_ingest.txt) and list one S3 key per line, for example:

```
2024_publications/2024-energy-efficiency-briefing-EN.pdf
2024_publications/2024-ccg-year-in-review.pdf
```

> **Careful:** if the file has no keys, **every PDF in the bucket is ingested** (330 PDFs). Start with a handful.

Each PDF must be small enough to send to the model in one piece (under 4.5 MB).

### 4. Ingest

```powershell
python ingest/1_start_ingestion.py
```

This only sends messages. The Lambdas do the work in the background, roughly 20 to 40 seconds per PDF, and the section embedding finishes about a minute after that. To watch progress, open the CloudWatch logs of the `askwri-sections` and `askwri-embed` Lambdas, or look at the message counts of the `askwri-pdf-queue` and `askwri-section-queue` queues in the SQS console.

**Re-ingesting a document replaces everything about it.** Run the script again with the same key and the old vectors, section files and document details are deleted and rebuilt from scratch. The one thing kept is a `source_url` you filled in by hand in the DynamoDB console.

### 5. Try the agent locally

Terminal 1, start the agent:

```powershell
$env:AWS_PROFILE="builder"
python agent/agent.py
```

It serves on `http://localhost:8080`. Terminal 2, start the chat page, with `AGENT_ARN = ""` at the top of [app/streamlit_app.py](app/streamlit_app.py) so it talks to your local agent:

```powershell
streamlit run app/streamlit_app.py
```

Open http://localhost:8501 and ask a question.

### 6. Deploy the agent to AgentCore (optional, for a hosted agent)

```powershell
cd agent
$env:AWS_PROFILE="builder"
$env:AWS_DEFAULT_REGION="us-east-1"
agentcore configure -e agent.py -n askwri_agent -rf requirements.txt -dm --non-interactive
agentcore deploy
```

Then:

1. Copy the **Agent ARN** from the deploy output into `AGENT_ARN` in [app/streamlit_app.py](app/streamlit_app.py).
2. Find the agent's execution role name in `agent/.bedrock_agentcore.yaml` (the `execution_role` line, the part after `role/`), put it in a new file `terraform/terraform.tfvars` (it isn't committed to git) as `agent_role_name = "..."`, and apply again so the agent is allowed to read the data:

```powershell
cd ..\terraform
terraform apply
cd ..
```

3. Run `streamlit run app/streamlit_app.py`. It now calls the hosted agent.

After you change `agent/agent.py`, run `agentcore deploy` again from `agent/`.

---

## Example questions

- *"How fast did China's energy intensity fall during the 11th Five-Year Plan?"* (a normal question, answered with citations)
- *"Write a briefing on carbon pricing."* (a research briefing)
- *"Where are the gaps in WRI's research on energy efficiency?"* (the gaps agent, with "Suggestion:" lines)
- *"What is WRI's position on cryptocurrency?"* (not in the documents, so it answers: "I couldn't find this in the WRI documents I have access to.")

---

## Changing the tags, regions or topics

Edit the lists in [lambdas/labels.py](lambdas/labels.py) and copy the **identical** file to [agent/labels.py](agent/labels.py). Then run `terraform apply` (updates the Lambda), `agentcore deploy` (updates the agent), and re-ingest the documents so they get the new labels.

---

## Using this in a different AWS account

These account-specific values appear in the code and must be changed:

| Value | Where |
|---|---|
| Source PDF bucket `wri-bucket-6157-5871-0841` | `ingest/common.py`, `lambdas/sections_handler.py`, `terraform/main.tf` |
| Sections bucket `askwri-sections-615758710841` (it ends with the account id) | `agent/agent.py` |
| Agent ARN | `app/streamlit_app.py` (set in step 6) |
| Agent role name | `terraform/terraform.tfvars` (you create it in step 6) |
| AWS profile `builder` and region `us-east-1` | `ingest/common.py`, `app/streamlit_app.py`, `terraform/main.tf` |

---

## Known limitations

- **No login.** Anyone who can reach the Streamlit page can use it. Don't expose it publicly as is.
- **No dead-letter queue.** If a PDF keeps failing, SQS retries it until the message expires (1 hour) and then drops it. Check the Lambda logs if a document never appears.
- **Search finds the closest matches, it can't prove something is absent.** The gaps agent combines the document inventory (`list_documents`) with searches, but "gaps" always means gaps within the documents that were ingested.
- **Tables and figures are ignored** during ingestion; only text is searchable.
- **Large PDFs:** one PDF must fit in one model call. Very long documents may be cut off.
- **Re-ingesting scans the whole vector index** to find the old vectors, which is fine for hundreds of documents but gets slower as the index grows.

---

## Tearing it down

```powershell
cd agent
agentcore destroy          # removes the hosted agent
cd ..\terraform
terraform destroy          # removes everything Terraform created
```

`terraform destroy` fails on the sections bucket while it still contains files; empty the bucket first (S3 console, or `aws s3 rm s3://askwri-sections-<account-id> --recursive`).

# AskWRI

AskWRI is a chatbot that answers questions using World Resources Institute (WRI) research PDFs.

- Every answer **cites its source**: document title, pages, link (if known) and a quoted passage.
- If the documents don't contain the answer, it says so instead of guessing.
- It can write a **research briefing** on a topic.
- It can map **where WRI's research has gaps** on a topic and suggest follow-up research.

It runs entirely on AWS (Amazon Bedrock, S3, DynamoDB, SQS, Lambda, AgentCore). The chat page is a small Streamlit app.

---

## Quick start: deploy it into your own AWS account

You need Python 3.12, Terraform, the AWS CLI, and an AWS account with Amazon Bedrock model access in **us-east-1** (Claude Sonnet 5.5, Claude Haiku 5.5, Titan Text Embeddings V2). Use a **US region** (`us-east-1`, `us-east-2` or `us-west-2`): the AI model ids in the code start with `us.`, so other regions don't work, and Terraform refuses to run outside them. Only `us-east-1` has been tested. Run all commands from the repo root, in a terminal on Windows (PowerShell), macOS or Linux. They are identical on every system except for how you set your AWS profile (step A). On macOS/Linux, use `python3` and `pip3` in place of `python` and `pip` if those are the names on your machine.

### Step A: set your AWS profile and region, and edit these values (before running anything)

**Choose your AWS profile and region once per terminal window.** Every script, Terraform, the Lambdas, the agent and the chat page all use them automatically (no profile or region is written in the code). If your default profile already has a US region you can skip this.

```
# Windows PowerShell
$env:AWS_PROFILE = "YOUR_PROFILE_NAME"
$env:AWS_DEFAULT_REGION = "us-east-1"
```

```bash
# macOS / Linux
export AWS_PROFILE=YOUR_PROFILE_NAME
export AWS_DEFAULT_REGION=us-east-1
```

(If your profile already has a US region set, `AWS_DEFAULT_REGION` isn't needed. You can set one with `aws configure --profile YOUR_PROFILE_NAME`.)

Use the same terminal window for all the commands below (if you open a new window, set it again). To check it works, run `aws sts get-caller-identity`; it should show your AWS account.

Then edit these values:

| # | File | Line to change | Put |
|---|---|---|---|
| 1 | `terraform/main.tf` | `source_bucket = "wri-bucket-6157-5871-0841"` | the S3 bucket that holds your PDFs |
| 2 | `lambdas/sections_handler.py` | `SOURCE_BUCKET = "wri-bucket-6157-5871-0841"` | the same PDF bucket |
| 3 | `ingest/common.py` | `SOURCE_BUCKET = "wri-bucket-6157-5871-0841"` | the same PDF bucket |
| 4 | `docs_to_ingest.txt` | the list of keys | the PDFs you want to ingest, one S3 key per line (e.g. `2024_publications/some-file.pdf`) |

> **Careful with step A4:** if `docs_to_ingest.txt` has no keys, **every PDF in the bucket is ingested** (it could be hundreds).

### Step B: run these commands in order

**1. Install the Python packages**
```
pip install -r requirements.txt
```

**2. Package the agent.** This builds `agent/agent_code.zip` (the agent code plus its libraries, for AgentCore's Linux machines). Terraform uploads it in the next step.
```
python agent/build_zip.py
```

**3. Create everything in AWS**: the tables, vector index, buckets, queues, Lambdas and the AgentCore agent. Type `yes` when asked. It takes a few minutes.
```
cd terraform
terraform init
terraform apply
cd ..
```

**4. Ingest your PDFs.** This only queues them; the Lambdas then work in the background (about 20 to 40 seconds per PDF, plus about a minute for embedding).
```
python ingest/1_start_ingestion.py
```

**5. Open the chat page.** It finds your agent by its name (`askwri_agent`), so there is nothing to copy.
```
streamlit run app/streamlit_app.py
```
Go to http://localhost:8501. Try the example questions further down. (`terraform output agent_runtime_arn` shows the agent's ARN if you ever need it.)

**After you change `agent/agent.py` or `agent/labels.py`:** run `python agent/build_zip.py` and then `terraform apply` again (from `terraform/`). Terraform uploads the new zip and updates the agent.

The rest of this README explains how everything works and covers details such as re-ingesting, running the agent locally, and tearing down.

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
| `show_coverage_dashboard` | Gaps agent only, and only for questions about the library as a whole (or when asked for a dashboard). Draws how many documents are loaded by topic, region and year, counted from the library's metadata by code, so the numbers are exact. Zeros show gaps. It shows at most once per question. |
| `show_chart` | Draws a bar, horizontal bar, line or pie chart under an answer, only when it helps (a trend, comparison or ranking with three or more numbers, or when you ask for a chart; never for a single number or a simple fact). The agent may only chart numbers that appear in the documents it read, and must say which sources they come from. |
| `suggest_followups` | Offers 2 to 3 next questions as buttons under the answer. |

The three display tools don't draw anything themselves. They record what to show, and the chat page draws it (with Streamlit's built-in charts) next to the answer.

Limits per question: each sub-agent can search at most 5 times, a section is never given to the agent twice, and citation numbers are unique. The allowed values for `region`, `topic` and `tag` are built into the tool definitions, so the agent can't invent one.

---

## What's in this repository

```
README.md                 this file
SPEC.md                   the full build specification (the source of truth)
requirements.txt          Python packages for the scripts and the Streamlit app
docs_to_ingest.txt        which PDFs to ingest (one S3 key per line; empty = ALL PDFs)
terraform/                all infrastructure as code (tables, buckets, queues, Lambdas, the agent, IAM)
lambdas/
  sections_handler.py     Lambda 1: PDF -> section text files + metadata
  embed_handler.py        Lambda 2: section -> chunks -> vectors
  labels.py               the allowed tags, regions and topics
ingest/
  common.py               settings and helper to read docs_to_ingest.txt
  1_start_ingestion.py    sends one SQS message per PDF
agent/
  agent.py                the chat agent (runs on AgentCore)
  build_zip.py            packages the agent into agent_code.zip for Terraform
  labels.py               copy of lambdas/labels.py (keep them identical!)
  requirements.txt        packages the deployed agent needs
app/
  streamlit_app.py        the chat page
evaluation/               tests the deployed agent on 23 questions (see evaluation/README.md)
.streamlit/
  config.toml             the page's colours and settings
```

---

## Before you start

You need:

- **Python 3.12** and `pip`
- **Terraform** (1.5 or newer)
- An **AWS account** with permission to create the resources above, and an AWS CLI profile with credentials (set up with `aws configure --profile YOUR_PROFILE_NAME`). Its region must be a US region (see the Quick start).
- **Amazon Bedrock model access** in your region for: Claude Sonnet 5.5 (`us.anthropic.claude-sonnet-5-5`), Claude Haiku 5.5 (`us.anthropic.claude-haiku-5-5`) and Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`).
- The PDFs in an S3 bucket your profile can read (the original project used `wri-bucket-6157-5871-0841`, folder `2024_publications/`). Each PDF must be under 4.5 MB.

---

## The steps in more detail

The Quick start at the top is all you need to follow. This section explains what the steps do, and covers re-ingesting and running the agent on your own computer.

### What `python agent/build_zip.py` does
AgentCore runs the agent on its own Linux ARM64 machines, so the agent's Python libraries have to be downloaded for that platform (not for your PC) and zipped together with `agent.py` and `labels.py`. The script does exactly that and writes `agent/agent_code.zip` (about 25 MB). Run it again whenever you change `agent/agent.py` or `agent/labels.py`, then run `terraform apply`. Terraform sees the new zip, uploads it, and updates the agent.

### What `terraform apply` creates
The DynamoDB table (document details), the S3 Vectors bucket and index (searchable chunks), the S3 bucket for section text files, the two SQS queues, the two Lambdas with their permissions, an S3 bucket for the agent's code zip, the agent's IAM role, and the AgentCore agent itself (`askwri_agent`).

### Choosing which PDFs to ingest
List one S3 key per line in [docs_to_ingest.txt](docs_to_ingest.txt), for example:

```
2024_publications/2024-energy-efficiency-briefing-EN.pdf
2024_publications/2024-ccg-year-in-review.pdf
```

> **Careful:** if the file has no keys, **every PDF in the bucket is ingested** (330 PDFs). Start with a handful.

Each PDF must be small enough to send to the model in one piece (under 4.5 MB).

### Ingesting
`python ingest/1_start_ingestion.py` only sends messages. The Lambdas do the work in the background, roughly 20 to 40 seconds per PDF, and the section embedding finishes about a minute after that. To watch progress, open the CloudWatch logs of the `askwri-sections` and `askwri-embed` Lambdas, or look at the message counts of the `askwri-pdf-queue` and `askwri-section-queue` queues in the SQS console.

**Re-ingesting a document replaces everything about it.** Run the script again with the same key and the old vectors, section files and document details are deleted and rebuilt from scratch. The one thing kept is a `source_url` you filled in by hand in the DynamoDB console.

### Running the agent on your own computer (optional)
Instead of the hosted agent, you can run it locally. Terminal 1:

```
python agent/agent.py
```

It serves on `http://localhost:8080`. Terminal 2: set `USE_LOCAL_AGENT = True` at the top of [app/streamlit_app.py](app/streamlit_app.py) so the chat page talks to your local agent, then run `streamlit run app/streamlit_app.py`.

---

## Example questions

- *"How fast did China's energy intensity fall during the 11th Five-Year Plan?"* (a normal question, answered with citations)
- *"Write a briefing on carbon pricing."* (a research briefing)
- *"Where are the gaps in WRI's research on energy efficiency?"* (the gaps agent, with "Suggestion:" lines)
- *"What is WRI's position on cryptocurrency?"* (not in the documents, so it answers: "I couldn't find this in the WRI documents I have access to.")

**Using the page:** type a question, or click one of the three examples on the empty chat. To get a briefing or a gaps analysis, just ask for one ("write a briefing on…", "where are the gaps in…"); name a region or topic in the question to focus on it. Under each answer, a "Sources" list shows the documents and sections the answer was built from. Click one to open the original PDF in a pane on the right (scroll it like any PDF; "Open in a new tab at page N" jumps to the section's page). If an answer comes from only one document, a "Single source" note says so. Gaps answers about the whole library start with a dashboard of what it covers, and an answer can include a chart of numbers quoted in the documents. The agent also suggests a few follow-up questions as buttons.

**Language selector:** when the library holds documents in more than one language, a "Search documents in" dropdown appears. Pick a language and every agent only searches, lists and counts documents written in that language (it is applied in code, not left to the model). Answers are always in English, and the PDF you open is the original in its own language. Each document's language is chosen by the model during ingestion from a fixed list in `lambdas/labels.py`.

PDFs open from temporary links that the agent creates (its role is allowed to read the PDF bucket, set up in Terraform), so the person using the page needs no access to that bucket. A link works for up to an hour. If you open a source from an older answer, or a link has stopped working, the page quietly asks the agent for a fresh one (a quick request that doesn't re-answer the question). Anyone who has a link can read that PDF until it expires.

---

## Evaluating the agent

The agent sends its traces to CloudWatch (it starts with `opentelemetry-instrument`), and
[evaluation/](evaluation/README.md) uses them to score the deployed agent on 23 test questions with
AgentCore batch evaluation, in about 4.5 minutes:

```
pip install -r requirements.txt -r evaluation/requirements.txt
python evaluation/run_batch_eval.py --label my-baseline
```

New to it? Start with [Your first run](evaluation/README.md#your-first-run-about-10-minutes) in
evaluation/README.md: it covers the prerequisites, reading the report, the current baseline and
its findings, and comparing runs.

---

## Changing the tags, regions, topics or languages

Edit the lists in [lambdas/labels.py](lambdas/labels.py) and copy the **identical** file to [agent/labels.py](agent/labels.py). Then run `python agent/build_zip.py` and `terraform apply` (this updates both the Lambda and the agent), and re-ingest the documents so they get the new labels.

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

```
cd terraform
terraform destroy          # type "yes"; removes everything, including the stored documents and vectors
```

Everything is in Terraform, so this one command removes it all.

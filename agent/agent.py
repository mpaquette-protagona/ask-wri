"""The AskWRI agent. An orchestrator hands questions to a research agent or a gaps agent.
They find WRI sections with a search tool (semantic search plus metadata filters).
Runs on AgentCore Runtime.
"""
import json
import urllib.parse
from typing import Literal, Optional

import boto3
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from labels import REGIONS, TAGS, TOPICS

# ---- Constants ----
REGION = "us-east-1"
DOCS_TABLE = "askwri-documents"
VECTOR_BUCKET = "askwri-vectors"
VECTOR_INDEX = "askwri-index"
CHAT_MODEL = "us.anthropic.claude-sonnet-5-5"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
MAX_SEARCHES = 5        # search_wri calls allowed per question for the research agent
GAPS_MAX_SEARCHES = 12  # the gaps agent must read many documents, so it gets more

ORCHESTRATOR_PROMPT = """You are AskWRI, the front desk for World Resources Institute (WRI) research.
Send questions and briefing requests to research_agent. Send questions about coverage, gaps,
or what WRI has not yet studied to gaps_agent. Include relevant context from earlier in the
conversation in the request you pass on. Return the agent's answer to the user unchanged,
including every citation. Never answer from your own knowledge."""

SOURCES_RULES = """Citations and Sources:
- End every factual sentence with a citation like [1]. Use only numbers from the [SOURCE n] blocks you were given.
- Finish with a line that says exactly "## Sources", then a markdown list with ONE bullet per document
  (not per section): **Title** (Year; Regions; Topics, from the header), with a [link](URL) only if the
  header has a URL (URL: none means omit it).
  Under it, one nested bullet per cited section: [n] pp. X-Y: "short supporting quote". Use "p. X" when
  the first and last page are the same. Copy titles, pages and URLs exactly from the [SOURCE n] headers.
- Check every page range against its header before you finish. Never add corrections, apologies or notes
  about mistakes to the answer; fix the list instead."""

RESEARCH_PROMPT = """You answer ONLY from WRI documents returned by the search_wri tool. Never use outside knowledge.
- Search before answering. Use the region, topic or tag filter when the user names one.
- If search_wri returns NO_RESULTS, or the sections do not actually answer the question, reply
  exactly: "I couldn't find this in the WRI documents I have access to." and stop. Do not guess.
- If the user asks for a briefing, use exactly this structure, in this order:
  ## At a glance
  A markdown table with columns Figure | What it measures | Source, holding 4 to 6 headline numbers that
  appear in the sections you were given (each with its [n]). Under the table, one line:
  "Based on N WRI documents, FIRST YEAR to LAST YEAR, REGIONS", built only from the Year and Regions
  fields of the documents you actually cite. Never invent or round a number.
  ## Briefing
  Summary (3-4 sentences), then Key findings (bullets, each cited), then Related WRI publications
  (titles, with links only when a URL exists).
  ## Sources
""" + SOURCES_RULES

GAPS_PROMPT = """You map WRI's research coverage on a topic, using ONLY the documents in this library
(search_wri and list_documents). Never use outside knowledge.
Method: call list_documents with the matching tag, topic or region to see every matching document. Then read
each of them with search_wri, using its document filter, until the search limit. If there are more documents
than searches, name the ones you did not read and describe them only by title and tags.
Reply with exactly these parts, in this order:
1. A line starting "**In short:**" with two or three sentences giving the main finding.
2. A short italic line saying that gaps are relative to the documents loaded in this library, not to all of WRI's work.
3. "## What WRI has covered": cited findings grouped by document, every sentence ending with [n].
4. "## Where coverage is thin": a markdown table with columns Area | What is missing | Evidence. Evidence names
   the documents that show it, or says no document in the library covers it. Never say "WRI has not studied this";
   say "not in the loaded library".
5. "## Suggested research directions": every item starts with "Suggestion:".
6. "## Sources".
""" + SOURCES_RULES

# ---- AWS clients (no profile: AgentCore gives us an IAM role) ----
session = boto3.Session(region_name=REGION)
brt = session.client("bedrock-runtime")
s3v = session.client("s3vectors")
s3 = session.client("s3")
dynamodb = session.resource("dynamodb")
docs_table = dynamodb.Table(DOCS_TABLE)

# The sections bucket name ends with the AWS account id (same rule as in Terraform)
SECTIONS_BUCKET = "askwri-sections-" + session.client("sts").get_caller_identity()["Account"]

# ---- Per-question state: call counts, sections already returned, source numbering ----
state = {}


def reset_state():
    """Called at the start of every question."""
    state.update(searches=0, seen=set(), source_no=0, max_searches=MAX_SEARCHES)


reset_state()


def scan_documents():
    """Return every row of the documents table (follows pagination)."""
    docs = []
    response = docs_table.scan()
    docs += response["Items"]
    while "LastEvaluatedKey" in response:
        response = docs_table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        docs += response["Items"]
    return docs


def read_section(doc_id, section_id):
    """Read one section file from S3 and return it as a numbered [SOURCE n] block."""
    obj = s3.get_object(Bucket=SECTIONS_BUCKET, Key=f"sections/{doc_id}/{section_id}.txt")
    info = obj["Metadata"]  # title, page_start, page_end
    text = obj["Body"].read().decode("utf-8")
    doc = docs_table.get_item(Key={"doc_id": doc_id})["Item"]
    state["seen"].add((doc_id, section_id))
    state["source_no"] += 1
    first, last = info["page_start"], info["page_end"]
    pages = first if first == last else f"{first}-{last}"
    return (f"[SOURCE {state['source_no']}] Title: {doc.get('title', doc_id)} | "
            f"URL: {doc.get('source_url') or 'none'} | "
            f"Year: {doc.get('year', 'unknown')} | "
            f"Regions: {', '.join(doc.get('regions', [])) or 'none'} | "
            f"Topics: {', '.join(doc.get('topics', [])) or 'none'} | "
            f"Pages: {pages} | "
            f"Section: {urllib.parse.unquote(info['title'])}\n{text}")


# ---- Tool 1: search ----
# Literal types become "allowed values" lists in the tool definition the model sees.
Region = Literal[tuple(REGIONS)]
Topic = Literal[tuple(TOPICS)]
Tag = Literal[tuple(TAGS)]


@tool
def search_wri(query: str = "", region: Optional[Region] = None, topic: Optional[Topic] = None,
               tag: Optional[Tag] = None, document: str = "") -> str:
    """Find the most relevant full sections of WRI research documents, with citation details.
    Give a query (semantic search), and/or filters (region, topic, tag; each limits the search
    to documents with that value; document is a document id from list_documents and limits the
    search to that one document). At least one of them is required. Returns up to 5 sections
    you have not been given yet. The number of calls per question is limited."""
    if not (query or region or topic or tag or document):
        return "Give a query and/or at least one filter."
    if state["searches"] >= state["max_searches"]:
        return "RETRIEVAL_LIMIT_REACHED: no more searches allowed. Answer with what you have."
    state["searches"] += 1

    # 1. Embed the query (if there is no query, embed the filter values instead)
    text = query or " ".join(v for v in (topic, region, tag, document.replace("-", " ")) if v)
    body = json.dumps({"inputText": text, "dimensions": 1024, "normalize": True})
    resp = brt.invoke_model(modelId=EMBED_MODEL, body=body)
    vector = json.loads(resp["body"].read())["embedding"]

    # 2. Build the optional filter
    filters = []
    if region:
        filters.append({"regions": {"$eq": region}})
    if topic:
        filters.append({"topics": {"$eq": topic}})
    if tag:
        filters.append({"tags": {"$eq": tag}})
    if document:
        filters.append({"doc_id": {"$eq": document}})
    filter_kwargs = {}
    if len(filters) == 1:
        filter_kwargs["filter"] = filters[0]
    elif len(filters) > 1:
        filter_kwargs["filter"] = {"$and": filters}

    # 3. Vector search over the chunks
    hits = s3v.query_vectors(vectorBucketName=VECTOR_BUCKET, indexName=VECTOR_INDEX,
                             queryVector={"float32": vector}, topK=30,
                             returnMetadata=True, returnDistance=True, **filter_kwargs)["vectors"]
    if not hits:
        return "NO_RESULTS"

    # 4. Unique (doc_id, section_id) pairs that we have not returned yet, max 5
    pairs = []
    for hit in hits:
        pair = (hit["metadata"]["doc_id"], hit["metadata"]["section_id"])
        if pair not in pairs and pair not in state["seen"]:
            pairs.append(pair)
        if len(pairs) == 5:
            break
    if not pairs:
        return "NO_NEW_RESULTS: every matching section was already returned earlier."
    return "\n\n".join(read_section(doc_id, section_id) for doc_id, section_id in pairs)


# ---- Tool 2: list documents (used by the gaps agent) ----
@tool
def list_documents(tag: Optional[Tag] = None, region: Optional[Region] = None,
                   topic: Optional[Topic] = None) -> str:
    """List the WRI documents in the library (document id, title, year, regions, topics, tags),
    optionally filtered by tag, region or topic. Use a document id with search_wri's document filter."""
    lines = []
    for d in scan_documents():
        tags = list(d.get("tags", []))
        regions = list(d.get("regions", []))
        topics = list(d.get("topics", []))
        if tag and tag not in tags:
            continue
        if region and region not in regions:
            continue
        if topic and topic not in topics:
            continue
        lines.append(f"{d['doc_id']} | {d.get('title', '')} | {d.get('year', '')} | "
                     f"{', '.join(regions)} | {', '.join(topics)} | {', '.join(tags)}")
    return "\n".join(lines) or "No documents match."


MODEL = BedrockModel(model_id=CHAT_MODEL, region_name=REGION)


@tool
def research_agent(request: str) -> str:
    """Answer a question about WRI research, or write a research briefing, with citations."""
    state.update(searches=0, max_searches=MAX_SEARCHES)  # each sub-agent gets its own searches
    return str(Agent(model=MODEL, system_prompt=RESEARCH_PROMPT, tools=[search_wri])(request))


@tool
def gaps_agent(topic: str) -> str:
    """Map what WRI has published on a topic and suggest gaps and follow-up research."""
    state.update(searches=0, max_searches=GAPS_MAX_SEARCHES)
    return str(Agent(model=MODEL, system_prompt=GAPS_PROMPT, tools=[search_wri, list_documents])(topic))


orchestrator = Agent(model=MODEL, system_prompt=ORCHESTRATOR_PROMPT, tools=[research_agent, gaps_agent])

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    reset_state()  # new question: reset the call counts and the "already returned" list
    return {"answer": str(orchestrator(payload["prompt"]))}


if __name__ == "__main__":
    app.run()

"""The AskWRI agent. An orchestrator hands questions to a research agent or a gaps agent.
They find WRI sections with a search tool (semantic search plus metadata filters), and can also
show charts, a library coverage dashboard, and suggested follow-up questions on the chat page.
Runs on AgentCore Runtime.
"""
import json
import os
import urllib.parse
from collections import Counter
from typing import Literal, Optional

import boto3
from botocore.config import Config
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from labels import LANGUAGES, REGIONS, TAGS, TOPICS

# ---- Constants ----
DOCS_TABLE = "askwri-documents"
VECTOR_BUCKET = "askwri-vectors"
VECTOR_INDEX = "askwri-index"
CHAT_MODEL = "us.anthropic.claude-sonnet-5-5"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
RESEARCH_MAX_SEARCHES = 5  # search_wri calls the research agent may make per question
GAPS_MAX_SEARCHES = 10     # the gaps agent needs more, because it reads many documents

ORCHESTRATOR_PROMPT = """You are AskWRI, the front desk for World Resources Institute (WRI) research.
Send questions and briefing requests to research_agent. Send questions about coverage, gaps,
or what WRI has not yet studied to gaps_agent. Include relevant context from earlier in the
conversation in the request you pass on. Return the agent's answer to the user unchanged,
including every citation. Never answer from your own knowledge."""

RESEARCH_PROMPT = """You answer ONLY from WRI documents returned by the search_wri tool. Never use outside knowledge.
- Search before answering. Use the region or tag filter when the user names a region or topic.
- End every factual sentence with a citation like [1]. Sections from the same document share one
  number. Finish with a "Sources" heading and a markdown bullet list (start every line with "- "),
  one bullet per document: [n] Title, its page ranges (join several with commas; write a single page
  as "26", not "26-26"), the URL only if the source has one, then a short quoted passage that
  supports the claim.
- If search_wri returns NO_RESULTS, or the sections do not actually answer the question, reply
  exactly: "I couldn't find this in the WRI documents I have access to." and stop. Do not guess.
- If the user asks for a briefing, use this format: Summary (3-4 sentences), Key findings
  (bullets, each cited), Related WRI publications (titles and links), Sources.
- Call show_chart only when it truly helps: the user asks for a chart, graph or visual, or asks about
  a trend, comparison or ranking and the sources state three or more comparable numbers (for example
  by year, place or category). Never chart a single number, a simple fact, a list, or a descriptive
  answer. At most one chart. Chart ONLY numbers that appear in the sources, exactly as stated, never
  estimates, and say in the note which source numbers they come from.
- After an answer (not after the "couldn't find" reply), call suggest_followups with 2-3 natural next
  questions that the WRI documents could answer: one drill-down and one comparison."""

GAPS_PROMPT = """You map WRI's research coverage on a topic, using only the documents loaded in this library.
First call list_documents with the topic, region or tag filter that fits the request, so you see
every loaded document on it. Call show_coverage_dashboard (once) ONLY when the user asks about the
library as a whole (what it covers overall, which topics or regions are covered or missing) or asks
for a dashboard, overview or chart of it. Do NOT call it for a gap question about one narrow topic;
the written answer is enough there. It draws the number of loaded documents by topic, region and year
from the library's metadata and returns those counts (they need no [n] citation; a zero is a gap in
the loaded set). Then use search_wri (its document filter takes a document id from list_documents)
to read those documents, the most relevant first, until you reach your search limit. Also search by
query for anything those documents do not cover. Call show_chart only if the user asks for a chart,
or comparable numbers stated in the sources make a trend or comparison clearer (never estimates).
When you are done, call suggest_followups with 2-3 natural next questions.
Reply in exactly this order:
1. "Summary": three short bullet lines.
2. One italic line: this only covers the documents loaded in this library, so a gap means "not in
   the loaded set", not that WRI has not covered it. Never say "WRI hasn't covered this".
3. "What WRI has covered": cited, using [n] citations. Sections from the same document share one
   number.
4. "Where coverage is thin": a markdown table with the columns Area, What is thin or missing, Evidence.
5. "Suggested research directions". Start every suggestion with "Suggestion:".
6. A "Sources" heading with a markdown bullet list, one bullet per document: [n] Title, its page
   ranges joined with commas, the URL only if there is one."""

# ---- AWS clients (no profile: AgentCore gives us an IAM role) ----
# Terraform passes the region to the deployed agent in ASKWRI_REGION. When you run the agent on your
# own computer, it falls back to AWS_REGION or your AWS_DEFAULT_REGION / profile region.
REGION = (os.environ.get("ASKWRI_REGION") or os.environ.get("AWS_REGION")
          or boto3.Session().region_name or "us-east-1")
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
    state.update(searches=0, max_searches=RESEARCH_MAX_SEARCHES, seen=set(), doc_numbers={},
                 visuals=[], followups=[], read=[], pdfs={},  # these are shown on the chat page (pdfs: doc id -> link)
                 language="")  # "" = all languages; otherwise only documents in this language are used


reset_state()


def scan_documents():
    """Return every row of the documents table (follows pagination), in the chosen language only."""
    docs = []
    response = docs_table.scan()
    docs += response["Items"]
    while "LastEvaluatedKey" in response:
        response = docs_table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        docs += response["Items"]
    if state["language"]:
        docs = [d for d in docs if d.get("language") == state["language"]]
    return docs


BUCKET_REGIONS = {}  # bucket name -> region (looked up once)


def pdf_link(bucket, key):
    """A temporary link (valid up to an hour) to the source PDF, made with this agent's permissions,
    so the person using the chat page needs no AWS access to the PDF bucket. "" if it can't be made."""
    if not (bucket and key):
        return ""
    try:
        if bucket not in BUCKET_REGIONS:
            headers = s3.head_bucket(Bucket=bucket)["ResponseMetadata"]["HTTPHeaders"]
            BUCKET_REGIONS[bucket] = headers.get("x-amz-bucket-region", REGION)
        client = session.client("s3", region_name=BUCKET_REGIONS[bucket], config=Config(signature_version="s3v4"))
        return client.generate_presigned_url("get_object", ExpiresIn=3600, Params={
            "Bucket": bucket, "Key": key, "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": "inline"})
    except Exception:
        return ""


def read_section(doc_id, section_id):
    """Read one section file from S3 and return it as a [SOURCE n] block (n is per document)."""
    obj = s3.get_object(Bucket=SECTIONS_BUCKET, Key=f"sections/{doc_id}/{section_id}.txt")
    info = obj["Metadata"]  # title, page_start, page_end
    text = obj["Body"].read().decode("utf-8")
    doc = docs_table.get_item(Key={"doc_id": doc_id})["Item"]
    state["seen"].add((doc_id, section_id))
    if doc_id not in state["pdfs"]:  # one link per document
        state["pdfs"][doc_id] = pdf_link(doc.get("source_bucket", ""), doc.get("s3_key", ""))

    # Sections of the same document share one number, so each document is cited once
    number = state["doc_numbers"].setdefault(doc_id, len(state["doc_numbers"]) + 1)
    first, last = info["page_start"], info["page_end"]
    pages = first if first == last else f"{first}-{last}"  # "26", not "26-26"

    state["read"].append({"source": number, "doc_id": doc_id, "section_id": section_id,
                          "bucket": doc.get("source_bucket", ""), "s3_key": doc.get("s3_key", ""),
                          "document": doc.get("title", doc_id),
                          "section": urllib.parse.unquote(info["title"]), "pages": str(pages)})
    header = [f"[SOURCE {number}] Title: {doc.get('title', doc_id)}"]
    if doc.get("source_url"):  # leave the URL out when we don't have one
        header.append(f"URL: {doc['source_url']}")
    header += [f"Pages: {pages}", f"Section: {urllib.parse.unquote(info['title'])}"]
    return " | ".join(header) + "\n" + text


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
    you have not been given yet. The number of searches you may make is limited; the tool tells
    you when you have reached the limit."""
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
    if state["language"]:  # the user limited the library to one language: always applied
        filters.append({"language": {"$eq": state["language"]}})
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


# ---- Tools that put visuals on the chat page (they only record what to show; the page draws it) ----
def make_chart(title, chart_type, labels, series, unit="", note=""):
    """Check a chart description and return it as a dict, or return an error message (str)."""
    if not labels or not series or len(labels) > 30 or len(series) > 4:
        return "Chart not added: give 1-30 labels and 1-4 series."
    for name, values in series.items():
        if len(values) != len(labels):
            return f"Chart not added: series '{name}' needs exactly {len(labels)} numbers, one per label."
    return {"chart_type": chart_type, "title": title, "labels": list(labels),
            "series": {name: list(values) for name, values in series.items()},
            "unit": unit, "note": note}


@tool
def show_chart(title: str, chart_type: Literal["bar", "barh", "line", "pie"], labels: list[str],
               series: dict[str, list[float]], unit: str = "", note: str = "") -> str:
    """Show a chart under your answer, but only when it helps: a trend, comparison or ranking with
    three or more numbers, or when the user asks for a chart. Not for a single number, a simple fact
    or a list. Use ONLY numbers that appear in the documents you were given, exactly as stated,
    never estimates. chart_type: bar (compare categories), barh (rankings),
    line (a trend over time), pie (shares of a whole). labels: the categories, for example years.
    series: a dict from series name to one number per label. unit: for example "% per year".
    note: which source numbers the data comes from, for example "Source [1]"."""
    chart = make_chart(title, chart_type, labels, series, unit, note)
    if isinstance(chart, str):
        return chart
    state["visuals"].append({"kind": "chart", **chart})
    return "Chart added to the page."


@tool
def show_coverage_dashboard() -> str:
    """Show a dashboard of what is loaded in the library: the number of documents by topic, by region
    and by year, taken from the library's metadata. Returns the counts. A zero is a gap in the
    loaded set. Use it only for questions about the whole library, or when the user asks for a
    dashboard or overview. Not for a question about one narrow topic."""
    if any(visual["kind"] == "dashboard" for visual in state["visuals"]):
        return "The dashboard is already shown on the page. Do not call this again."
    docs = scan_documents()
    topic_counts = Counter(t for d in docs for t in d.get("topics", []))
    region_counts = Counter(r for d in docs for r in d.get("regions", []))
    year_counts = Counter(d["year"] for d in docs if d.get("year"))
    by_topic = {t: topic_counts[t] for t in TOPICS}  # every topic, so missing ones show as 0
    by_region = {r: region_counts[r] for r in REGIONS}
    by_year = dict(sorted(year_counts.items()))

    def chart(title, chart_type, counts):
        return make_chart(title, chart_type, list(counts), {"Documents": list(counts.values())})

    state["visuals"].append({
        "kind": "dashboard", "title": "What the library covers",
        "kpis": [{"label": "Documents", "value": str(len(docs))},
                 {"label": "Topics covered", "value": f"{sum(1 for n in by_topic.values() if n)} of {len(TOPICS)}"},
                 {"label": "Regions covered", "value": f"{sum(1 for n in by_region.values() if n)} of {len(REGIONS)}"}],
        "charts": [chart("By topic", "barh", by_topic), chart("By region", "bar", by_region),
                   chart("By year", "bar", by_year)],
        "note": (f"Counts of loaded {LANGUAGES[state['language']]} documents only."
                 if state["language"] else
                 "Counts of loaded documents (copies in different languages count separately).")})
    return (f"Dashboard shown. Documents: {len(docs)}. By topic: {by_topic}. "
            f"By region: {by_region}. By year: {by_year}.")


@tool
def suggest_followups(questions: list[str]) -> str:
    """Offer 2-3 natural next questions as buttons under your answer: one drill-down and one
    comparison. Only suggest questions the WRI documents could answer."""
    state["followups"] = [q for q in questions if q.strip()][:3]
    return "Follow-up questions added to the page."


MODEL = BedrockModel(model_id=CHAT_MODEL, region_name=REGION)


@tool
def research_agent(request: str) -> str:
    """Answer a question about WRI research, or write a research briefing, with citations."""
    state.update(searches=0, max_searches=RESEARCH_MAX_SEARCHES)  # each sub-agent gets its own searches
    tools = [search_wri, show_chart, suggest_followups]
    return str(Agent(model=MODEL, system_prompt=RESEARCH_PROMPT, tools=tools)(request))


@tool
def gaps_agent(topic: str) -> str:
    """Map what WRI has published on a topic and suggest gaps and follow-up research."""
    state.update(searches=0, max_searches=GAPS_MAX_SEARCHES)  # each sub-agent gets its own searches
    tools = [search_wri, list_documents, show_coverage_dashboard, show_chart, suggest_followups]
    return str(Agent(model=MODEL, system_prompt=GAPS_PROMPT, tools=tools)(topic))


orchestrator = Agent(model=MODEL, system_prompt=ORCHESTRATOR_PROMPT, tools=[research_agent, gaps_agent])

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload):
    if payload.get("action") == "pdf_link":  # the chat page wants a fresh link to a source PDF
        doc = docs_table.get_item(Key={"doc_id": payload["doc_id"]}).get("Item", {})
        return {"url": pdf_link(doc.get("source_bucket", ""), doc.get("s3_key", ""))}
    reset_state()  # new question: reset the call counts and the "already returned" list
    if payload.get("language") in LANGUAGES:  # the chat page's language selector ("" = all languages)
        state["language"] = payload["language"]
    answer = str(orchestrator(payload["prompt"]))
    # Also report the evidence behind the answer, any charts or dashboard, and suggested follow-ups
    # (the chat page shows these)
    return {"answer": answer, "documents": len(state["doc_numbers"]), "sections": len(state["seen"]),
            "visuals": state["visuals"], "followups": state["followups"], "read": state["read"],
            "pdfs": state["pdfs"]}


if __name__ == "__main__":
    app.run()

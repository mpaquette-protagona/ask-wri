"""The AskWRI agent. The page's mode picks a research agent (questions, briefings) or a gaps agent.
They find WRI sections with a search tool (semantic search plus metadata filters).
Runs on AgentCore Runtime.
"""
import json
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional

import boto3
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from labels import REGIONS, TAGS, TOPICS
from passages import cited_numbers, excerpt, locate_quote, parse_quotes, split_answer

# ---- Constants ----
REGION = "us-east-1"
DOCS_TABLE = "askwri-documents"
VECTOR_BUCKET = "askwri-vectors"
VECTOR_INDEX = "askwri-index"
CHAT_MODEL = "us.anthropic.claude-sonnet-5-5"
EMBED_MODEL = "amazon.titan-embed-text-v2:0"
MAX_SEARCHES = 5        # search_wri calls allowed per question for the research agent
GAPS_MAX_SEARCHES = 12  # the gaps agent must read many documents, so it gets more

SOURCES_RULES = """Citations:
- End every factual sentence with a citation like [1]. Use only numbers from the [SOURCE n] blocks you were given.
- Do NOT write a source list or titles of sources at the end. Instead, finish with a line that says exactly
  "=== QUOTES ===" (never translate or change it), then one line for each source number you cited, in this form:
  [n] "short quote copied exactly from that source's text"
  Copy the quote letter for letter, in the source's own language, even when your answer is in another language.
  The quote must be the passage that supports the claim, at most 160 characters. Write nothing after the quotes."""

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
  Then the quotes block described below.
""" + SOURCES_RULES

GAPS_PROMPT = """You map WRI's research coverage on a topic, using ONLY the documents in this library
(search_wri and list_documents). Never use outside knowledge.
Method: call list_documents with the matching tag, topic or region to see every matching document. Then read
each of them with search_wri, using its document filter, until the search limit. Make these searches together
in one step rather than one at a time. If there are more documents than searches, name the ones you did not
read and describe them only by title and tags.
Length: the reply, not counting the quotes block, must be 650 words or fewer. Be brief and specific.
Reply with exactly these parts, in this order:
1. A line starting "**In short:**" with two or three sentences giving the main finding.
2. A short italic line saying that gaps are relative to the documents loaded in this library, not to all of WRI's work.
3. "## What WRI has covered": cited findings grouped under each document's bold title. At most 3 bullets per
   document, each under 30 words and ending with [n]. For a document that is only tagged with the topic and
   is not mainly about it, write one bullet.
4. "## Where coverage is thin": a markdown table with columns Area | What is missing | Evidence, at most 6 rows.
   Evidence names the documents that show it, or says no document in the library covers it. Never say
   "WRI has not studied this"; say "not in the loaded library".
5. "## Suggested research directions": at most 5 items, one sentence each, every item starting with "Suggestion:".
6. The quotes block described below. Cite only the strongest sources, so that it stays short.
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
LOCK = threading.Lock()  # tool calls can run at the same time, so state changes happen under this lock
POOL = ThreadPoolExecutor(max_workers=10)  # reads the sections of one search in parallel


def reset_state():
    """Called at the start of every question."""
    state.update(searches=0, seen=set(), source_no=0, max_searches=MAX_SEARCHES,
                 retrieved={}, allowed=None)


reset_state()


_docs_cache = {"at": 0.0, "by_id": {}}
DOCS_CACHE_SECONDS = 300  # the documents table changes only when documents are (re)ingested


def scan_documents():
    """Return every row of the documents table. Cached for a few minutes: each question used to scan
    the table again, and every section read used to do its own lookup."""
    if time.time() - _docs_cache["at"] > DOCS_CACHE_SECONDS or not _docs_cache["by_id"]:
        docs = []
        response = docs_table.scan()
        docs += response["Items"]
        while "LastEvaluatedKey" in response:
            response = docs_table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            docs += response["Items"]
        _docs_cache.update(at=time.time(), by_id={d["doc_id"]: d for d in docs})
    return list(_docs_cache["by_id"].values())


def get_doc(doc_id):
    """One document row, from the cache (a row added in the last few minutes is fetched directly)."""
    doc = _docs_cache["by_id"].get(doc_id)
    if doc is None:
        with LOCK:
            doc = docs_table.get_item(Key={"doc_id": doc_id})["Item"]
        _docs_cache["by_id"][doc_id] = doc
    return doc


FACETS = {"topics": "topics", "regions": "regions", "subtypes": "subtype_label",
          "resource_types": "resource_type", "languages": "original_language"}


def allowed_doc_ids(filters):
    """Return the ids of documents that pass the sidebar filters, or None when no filter is set.
    Values inside one filter are alternatives (any of them); different filters must all match."""
    active = {name: set(values) for name, values in (filters or {}).items()
              if name in FACETS and values}
    if not active:
        return None
    allowed = set()
    for doc in scan_documents():
        for name, wanted in active.items():
            have = doc.get(FACETS[name], [])
            have = set(have) if isinstance(have, (list, set, tuple)) else {have}
            if not (have & wanted):
                break
        else:
            allowed.add(doc["doc_id"])
    return allowed


def read_section(number, doc_id, section_id, score, chunk_hits):
    """Read one section file from S3 and return it as a numbered [SOURCE n] block.
    Safe to run in several threads: it only reads, and stores its result under its own number."""
    obj = s3.get_object(Bucket=SECTIONS_BUCKET, Key=f"sections/{doc_id}/{section_id}.txt")
    info = obj["Metadata"]  # title, page_start, page_end
    text = obj["Body"].read().decode("utf-8")
    doc = get_doc(doc_id)
    first, last = info["page_start"], info["page_end"]
    state["retrieved"][number] = {
        "doc": doc, "section_id": section_id, "text": text,
        "section_title": urllib.parse.unquote(info["title"]),
        "page_start": int(first), "page_end": int(last),
        "score": score, "chunk_hits": chunk_hits}
    pages = first if first == last else f"{first}-{last}"
    return (f"[SOURCE {number}] Title: {doc.get('title', doc_id)} | "
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
    with LOCK:
        if state["searches"] >= state["max_searches"]:
            return "RETRIEVAL_LIMIT_REACHED: no more searches allowed. Answer with what you have."
        state["searches"] += 1
    scan_documents()  # make sure the document cache is filled before the section reads start

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
    if state["allowed"] is not None:  # sidebar filters chosen by the user
        if not state["allowed"]:
            return "NO_RESULTS"
        filters.append({"doc_id": {"$in": sorted(state["allowed"])}})
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

    # 4. Rank sections by relevancy. Each hit is one chunk; S3 Vectors returns its cosine distance, so the
    #    chunk's similarity is 1 - distance. A section's relevancy is its best chunk; chunk_hits counts how many
    #    of the top chunks fell in that section. The five best sections nobody has been given yet are returned.
    #    Each gets its source number now, under the lock, so searches running at the same time cannot clash.
    best, chunk_hits = {}, {}
    for hit in hits:
        pair = (hit["metadata"]["doc_id"], hit["metadata"]["section_id"])
        best[pair] = max(best.get(pair, -1.0), 1.0 - hit["distance"])
        chunk_hits[pair] = chunk_hits.get(pair, 0) + 1
    ranked = sorted(best, key=lambda pair: (-best[pair], -chunk_hits[pair]))
    with LOCK:
        numbered = []
        for pair in ranked:
            if pair in state["seen"]:
                continue
            state["seen"].add(pair)
            state["source_no"] += 1
            numbered.append((state["source_no"], *pair, round(best[pair], 4), chunk_hits[pair]))
            if len(numbered) == 5:
                break
    if not numbered:
        return "NO_NEW_RESULTS: every matching section was already returned earlier."
    return "\n\n".join(POOL.map(lambda item: read_section(*item), numbered))


# ---- Tool 2: list documents (used by the gaps agent) ----
@tool
def list_documents(tag: Optional[Tag] = None, region: Optional[Region] = None,
                   topic: Optional[Topic] = None) -> str:
    """List the WRI documents in the library (document id, title, year, regions, topics, tags),
    optionally filtered by tag, region or topic. Use a document id with search_wri's document filter."""
    lines = []
    for d in scan_documents():
        if state["allowed"] is not None and d["doc_id"] not in state["allowed"]:
            continue
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


# Earlier questions of this session (one runtime session = one conversation). The old orchestrator held
# this memory; it also rewrote every sub-agent answer word for word, which cost 8 to 17 seconds.
HISTORY = []
MAX_HISTORY = 4


def remember(request, answer_body):
    """Keep the question and the answer text, without [n] markers (those numbers belong to one answer only)."""
    HISTORY.append((request, re.sub(r"\s*\[\d+\]", "", answer_body)))
    del HISTORY[:-MAX_HISTORY]


def make_agent(mode):
    """A fresh agent for this question that already knows the earlier questions and answers."""
    messages = []
    for request, answer in HISTORY:
        messages += [{"role": "user", "content": [{"text": request}]},
                     {"role": "assistant", "content": [{"text": answer}]}]
    if mode == "gaps":
        return Agent(model=MODEL, system_prompt=GAPS_PROMPT, tools=[search_wri, list_documents], messages=messages)
    return Agent(model=MODEL, system_prompt=RESEARCH_PROMPT, tools=[search_wri], messages=messages)


app = BedrockAgentCoreApp()


MODE_REQUESTS = {
    "ask": "{q}",
    "briefing": "Write a research briefing on this topic: {q}",
    "gaps": "Map the gaps in WRI's research on this topic: {q}",
}


def build_result(answer):
    """Turn the model's answer into the structured result the chat page displays.
    Page numbers, titles and passages come from what the search tool returned, never from
    the model's own text. Only the quote comes from the model, and it is checked against the passage."""
    body, sources_text = split_answer(answer)
    cited = set(cited_numbers(body)) & set(state["retrieved"])
    quotes = parse_quotes(sources_text)
    sources = []
    for number in sorted(state["retrieved"]):
        item = state["retrieved"][number]
        doc, is_cited = item["doc"], number in cited
        quote = quotes.get(number) if is_cited else None
        span = locate_quote(quote, item["text"]) if quote else None
        text, highlight, cut_start, cut_end = excerpt(item["text"], span, 2500 if is_cited else 1200)
        sources.append({
            "n": number, "cited": is_cited, "doc_id": doc["doc_id"], "title": doc.get("title", ""),
            "year": str(doc.get("year", "")), "resource_type": doc.get("resource_type", ""),
            "subtype": doc.get("subtype_label", ""), "regions": list(doc.get("regions", [])),
            "topics": list(doc.get("topics", [])), "language": doc.get("original_language", ""),
            "url": doc.get("source_url", ""), "pages_total": int(doc["pages_total"]) if doc.get("pages_total") else None,
            "section_title": item["section_title"], "page_start": item["page_start"], "page_end": item["page_end"],
            "relevancy": item["score"], "chunk_hits": item["chunk_hits"],
            "quote": quote, "verified": (span is not None) if quote else None,
            "passage": {"text": text, "highlight": list(highlight) if highlight else None,
                        "cut_start": cut_start, "cut_end": cut_end}})
    cited_sources = [x for x in sources if x["cited"]]
    # One entry per document, most relevant first. A document is as relevant as its best section.
    by_doc = {}
    for x in sources:
        d = by_doc.setdefault(x["doc_id"], {
            "doc_id": x["doc_id"], "title": x["title"], "year": x["year"], "subtype": x["subtype"],
            "regions": x["regions"], "topics": x["topics"], "language": x["language"], "url": x["url"],
            "pages_total": x["pages_total"], "relevancy": 0.0, "cited": False, "sources": []})
        d["relevancy"] = max(d["relevancy"], x["relevancy"])
        d["cited"] = d["cited"] or x["cited"]
        d["sources"].append(x["n"])
    scores = {x["n"]: x["relevancy"] for x in sources}
    for d in by_doc.values():
        d["sources"].sort(key=lambda n: -scores[n])
    documents = sorted(by_doc.values(), key=lambda d: (-d["relevancy"], -len(d["sources"])))
    cited_docs = [d for d in documents if d["cited"]]
    shown = cited_docs or documents
    by_subtype = {}
    for d in shown:
        by_subtype[d["subtype"] or "Other"] = by_subtype.get(d["subtype"] or "Other", 0) + 1
    stats = {
        "documents_retrieved": len(documents), "documents_cited": len(cited_docs),
        "passages_retrieved": len(sources), "passages_cited": len(cited_sources),
        "years": sorted({d["year"] for d in shown if d["year"]}),
        "languages": sorted({d["language"] for d in shown if d["language"]}),
        "by_subtype": sorted(by_subtype.items(), key=lambda kv: -kv[1]),
        "matching_documents": None if state["allowed"] is None else len(state["allowed"])}
    return {"answer": answer, "body": body, "sources": sources, "documents": documents, "stats": stats}


@app.entrypoint
def invoke(payload):
    reset_state()  # new question: reset the call counts and the "already returned" list
    state["allowed"] = allowed_doc_ids(payload.get("filters"))
    request = MODE_REQUESTS.get(payload.get("mode", "ask"), "{q}").format(q=payload["prompt"])
    language = payload.get("language")
    if language and language.lower() not in ("auto", ""):
        request += f"\n\n(Write the answer in {language}.)"
    mode = payload.get("mode", "ask")
    state["max_searches"] = GAPS_MAX_SEARCHES if mode == "gaps" else MAX_SEARCHES
    answer = str(make_agent(mode)(request))
    result = build_result(answer)
    remember(request, result["body"])
    return result


if __name__ == "__main__":
    app.run()

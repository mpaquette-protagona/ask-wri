"""The AskWRI chat page: menu on the left, the cited answer in the middle, and the source
passage (with the supporting quote highlighted) on the right once an answer has sources.
Sends each question to the agent (local or on AgentCore). Styling is in style.css, text in i18n.py.
"""
import json
import os
import time
import uuid
from pathlib import Path

import boto3
import requests
import streamlit as st
from botocore.config import Config

import i18n
import ui

# Replace account_id with your AWS account id (or set the AGENT_ARN environment variable).
# Set it to "" to use the local agent.
AGENT_ARN = os.environ.get("AGENT_ARN", "arn:aws:bedrock-agentcore:us-east-1:account_id:runtime/askwri_agent-wPm1MF2o63")
LOCAL_URL = os.environ.get("LOCAL_URL", "http://localhost:8080/invocations")  # used when AGENT_ARN is ""
REGION = "us-east-1"
DOCS_TABLE = "askwri-documents"

MODES = ["ask", "briefing", "gaps"]


@st.cache_resource
def agent_client():
    # Gap analyses and briefings can take close to a minute; the boto3 default read timeout is 60 s.
    # No automatic retry, so a slow question is never run (and paid for) twice.
    config = Config(read_timeout=900, connect_timeout=10, retries={"max_attempts": 1})
    return boto3.Session(region_name=REGION).client("bedrock-agentcore", config=config)


@st.cache_data(ttl=600)
def library():
    """Read the document list once: how many publications there are and the years they cover."""
    try:
        table = boto3.Session(region_name=REGION).resource("dynamodb").Table(DOCS_TABLE)
        kwargs = dict(ProjectionExpression="#y", ExpressionAttributeNames={"#y": "year"})
        items = []
        while True:
            page = table.scan(**kwargs)
            items += page["Items"]
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    except Exception:
        return {"count": 0, "years": []}
    return {"count": len(items), "years": sorted({i["year"] for i in items if i.get("year")})}


def ask_agent(job):
    """Send the question to the agent and return its structured result."""
    payload = {"prompt": job["question"], "mode": job["mode"], "language": job["language"]}
    if not AGENT_ARN:
        result = requests.post(LOCAL_URL, json=payload, timeout=900).json()
    else:
        resp = agent_client().invoke_agent_runtime(agentRuntimeArn=AGENT_ARN,
                                                   runtimeSessionId=st.session_state.session_id,
                                                   payload=json.dumps(payload))
        result = json.loads(resp["response"].read())
    if not isinstance(result, dict) or "sources" not in result:
        raise RuntimeError(str(result)[:200] if not isinstance(result, dict) else result.get("error", "unexpected reply"))
    return result


# ---- small callbacks -------------------------------------------------------------------
def set_mode(mode):
    st.session_state.mode = mode


def go_home():
    """Back to the start screen. Earlier questions stay in the Recent list."""
    st.session_state.view = None
    st.session_state.mode = "ask"
    st.session_state.pop("queued", None)


def view_turn(index):
    st.session_state.view = index


def queue(question, mode):
    st.session_state.queued = {"question": question, "mode": mode}


def pick_source(index):
    chosen = st.session_state.get(f"pills_{index}")
    if chosen is not None:  # clicking the active chip again must not leave the panel empty
        st.session_state.src_n = chosen


def ordered_cited(result):
    """Cited source numbers, most relevant document first, and inside a document the best section first."""
    cited = {s["n"] for s in result["sources"] if s["cited"]}
    return [n for d in result["documents"] for n in d["sources"] if n in cited]


@st.dialog("AskWRI", width="large")
def all_documents(result, tr):
    st.markdown(f"**{tr('dialog_title')}**")
    st.caption(tr("dialog_caption"))
    by_number = {s["n"]: s for s in result["sources"]}
    for rank, document in enumerate(result["documents"], 1):
        mark = tr("cited") if document["cited"] else tr("not_cited")
        title = document["title"] if len(document["title"]) <= 70 else document["title"][:68].rstrip() + "\u2026"
        with st.expander(f"{rank}. {title} \u00b7 {ui.percent(document['relevancy'])} % \u00b7 {mark}"):
            st.html(f'<div class="src-title">{ui.esc(document["title"])}</div>'
                    f'<div class="src-meta">{ui.esc(ui.document_meta(document, tr))}</div>'
                    + ui.relevancy_html(document["relevancy"], tr))
            st.markdown(f"**{tr('passages_in_doc')}**")
            for number in document["sources"]:
                st.html(ui.source_html(by_number[number], tr))
            if document.get("url"):
                st.link_button(tr("open_document"), document["url"], key=f"open_{rank}")


# ---- page setup ------------------------------------------------------------------------
st.set_page_config(page_title="AskWRI", page_icon="\U0001F30D", layout="wide")
st.html(f"<style>{(Path(__file__).parent / 'style.css').read_text()}</style>")
if st.session_state.get("dark_mode"):  # light is the default; dark loads on top of it
    st.html(f"<style>{(Path(__file__).parent / 'style_dark.css').read_text()}</style>")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.turns = []
    st.session_state.view = None
    st.session_state.mode = "ask"
    st.session_state.src_turn = None
    st.session_state.src_n = None
    st.session_state.ui_lang = "en"
    st.session_state.dark_mode = False  # light is the default

# ---- top right: the language of the whole tool (interface and answers) -------------------
with st.container(key="top_bar"):
    st.selectbox("Language", list(i18n.UI_LANGUAGES), format_func=i18n.UI_LANGUAGES.get, key="ui_lang",
                 label_visibility="collapsed", accept_new_options=False)
    tr = i18n.Tr(st.session_state.ui_lang)
    st.toggle(tr("dark_mode"), key="dark_mode", label_visibility="collapsed")  # sun and moon are drawn by style.css

lib = library()
turns = st.session_state.turns

# ---- left column: logo (home), menu, recent questions ---------------------------------------
with st.sidebar:
    st.button("AskWRI", key="brand_home", type="tertiary", on_click=go_home, help="Home")
    for mode in MODES:
        st.button(tr(f"nav_{mode}"), key=f"nav_{mode}", use_container_width=True, on_click=set_mode, args=(mode,),
                  type="primary" if st.session_state.mode == mode else "secondary")
    if turns:
        st.html(f'<div class="side-head">{ui.esc(tr("recent"))}</div>')
        for index, turn in list(enumerate(turns))[::-1][:8]:
            text = turn["question"] if len(turn["question"]) <= 38 else turn["question"][:36].rstrip() + "\u2026"
            st.button(text, key=f"recent_{index}", use_container_width=True, on_click=view_turn, args=(index,),
                      type="primary" if index == st.session_state.view else "secondary", help=turn["question"])

# ---- decide what to run (typed question, example button, or "Turn into briefing") --------
mode = st.session_state.mode
job = st.session_state.pop("queued", None)
typed = st.chat_input(tr(f"hint_{mode}"), key=f"input_{mode}")
if typed:
    job = {"question": typed.strip(), "mode": mode}
if job:
    job.update(language=tr.answer_language)

view = st.session_state.view
turn = turns[view] if (not job and view is not None and view < len(turns)) else None
has_sources = turn is not None and any(s["cited"] for s in turn["result"]["sources"])

# The source panel only exists once an answer has sources to show
if has_sources:
    center, right = st.columns([5, 4], gap="small")
else:
    center, right = st.container(), None

# ---- middle column ----------------------------------------------------------------------
with center:
    if job:
        st.html(ui.question_html(job["question"], tr(f"mode_{job['mode']}") if job["mode"] != "ask" else None))
        failed = False
        with st.status(tr("searching")) as status:
            started = time.time()
            try:
                result = ask_agent(job)
            except Exception as error:
                failed = True
                status.update(label=tr("error_title"), state="error")
                st.error(tr("error_body", error=type(error).__name__))
        if not failed:
            turns.append({**job, "result": result, "seconds": round(time.time() - started)})
            st.session_state.view = len(turns) - 1
            st.rerun()

    elif turn is None:
        years = lib["years"]
        st.html(f'<div class="hero"><div class="hero-title">{ui.esc(tr("hero_title"))}</div>'
                f'<div class="hero-sub">{ui.esc(tr("hero_sub", count=lib["count"], first=years[0] if years else "", last=years[-1] if years else ""))}</div></div>')
        for example_mode in MODES:
            st.button(f"{tr(f'nav_{example_mode}')}: {tr(f'example_{example_mode}')}", key=f"example_{example_mode}",
                      use_container_width=True, on_click=queue, args=(tr(f"example_{example_mode}"), example_mode))

    else:
        result, stats, documents = turn["result"], turn["result"]["stats"], turn["result"]["documents"]
        ordered = ordered_cited(result)

        # header: short title and "Turn into briefing"
        head, brief_col = st.columns([6, 3], vertical_alignment="center")
        title = turn["question"] if len(turn["question"]) <= 40 else turn["question"][:38].rstrip() + "\u2026"
        head.html(f'<div class="c-title">{ui.esc(title)}</div>')
        with brief_col:
            if turn["mode"] == "ask":
                st.button(tr("turn_into_briefing"), key=f"brief_{view}", type="primary", use_container_width=True,
                          on_click=queue, args=(turn["question"], "briefing"))

        st.html(ui.question_html(turn["question"], tr(f"mode_{turn['mode']}") if turn["mode"] != "ask" else None))

        # "What the search found": documents only; passages are inside the document list
        if not stats["documents_cited"]:
            badge, note = tr("badge_none"), tr("note_none")
        elif stats["documents_cited"] == 1:
            cited_doc = next(d for d in documents if d["cited"])
            badge = tr("badge_single")
            note = tr("note_single", kind=tr.label("subtype", cited_doc["subtype"] or "Other").lower())
        else:
            badge, note = tr("badge_many", n=stats["documents_cited"]), tr("note_many", n=stats["documents_cited"])
        with st.container(key=f"found_{view}"):
            st.html(ui.found_html(stats, badge, tr))
            note_col, button_col = st.columns([5, 3], vertical_alignment="center")
            note_col.html(f'<div class="found-note">{ui.esc(note)}</div>')
            if documents and button_col.button(tr("view_all", n=len(documents)), key=f"all_{view}",
                                               use_container_width=True):
                all_documents(result, tr)

        # the answer, with citation chips
        with st.container(key=f"answer_{view}"):
            st.markdown(ui.prepare_body(result["body"], {s["n"] for s in result["sources"] if s["cited"]}),
                        unsafe_allow_html=True)
        st.caption(tr("answered_in", seconds=turn["seconds"]))

        # source chips, most relevant first: choose which passage the right-hand panel shows
        if ordered:
            if st.session_state.src_turn != view:
                st.session_state.src_turn, st.session_state.src_n = view, ordered[0]
            st.html(f'<div class="side-head">{ui.esc(tr("sources_heading"))}</div>')
            by_number = {s["n"]: s for s in result["sources"]}
            labels = {n: f"{n} \u00b7 " + (by_number[n]["title"][:34].rstrip() + ("\u2026" if len(by_number[n]["title"]) > 34 else ""))
                      for n in ordered}
            st.pills(tr("sources_heading"), ordered, key=f"pills_{view}", default=st.session_state.src_n,
                     format_func=labels.get, label_visibility="collapsed", on_change=pick_source, args=(view,))

# ---- right column: the passage (only when there are sources) ----------------------------
if right is not None:
    with right:
        with st.container(key="source_panel"):
            by_number = {s["n"]: s for s in turn["result"]["sources"]}
            shown = by_number.get(st.session_state.src_n)
            if not shown or not shown["cited"]:
                shown = by_number[ordered_cited(turn["result"])[0]]
            st.html(ui.source_html(shown, tr))
            if shown.get("url"):
                st.link_button(tr("open_document"), shown["url"])

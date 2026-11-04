"""The AskWRI chat page. Sends each question to the agent (local or on AgentCore)
and shows the answer with its citations, sources and any charts. Clicking a source opens the PDF.
"""
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import altair as alt  # installed with Streamlit
import boto3
import pandas as pd  # installed with Streamlit
import requests
import streamlit as st
from botocore.config import Config

# The language names live in agent/labels.py (one copy, shared with the agent and the Lambda)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agent"))
from labels import LANGUAGES  # noqa: E402

# While a source PDF is open the page is wide (chat on the left, PDF on the right); otherwise centered.
viewing = st.session_state.get("viewing")
st.set_page_config(page_title="AskWRI", page_icon="🌍", layout="wide" if viewing else "centered")

AGENT_NAME = "askwri_agent"  # the agent's name in Terraform (agent.tf); we look up its ARN by name
USE_LOCAL_AGENT = False      # True = talk to `python agent/agent.py` running on this computer
LOCAL_URL = "http://localhost:8080/invocations"
DOCS_TABLE = "askwri-documents"
PALETTE = ["#2F6B4F", "#7FA893", "#C9A227", "#8A5A44", "#5B7C99"]  # chart colours (match the theme)

# Clickable examples shown on an empty chat. Each one asks for a chart and was tested to draw one.
EXAMPLES = [
    "How much international climate finance has China provided? Chart the amounts by year or by type.",
    "How fast has global energy efficiency improved compared with the rate needed through 2030? Chart it.",
    "Compare how fast energy intensity fell in the US (1950-2022 and 1970-2022) and in China (1980-2000 and 2006-2010). Chart it.",
]
# Used under an answer only when the agent did not suggest follow-up questions itself
FOLLOW_UPS = {
    "Turn into briefing": "Turn your previous answer into a research briefing.",
    "Find gaps on this": "Find the gaps in WRI's research on the topic of my previous question.",
}

# Keep the PDF pane in view while the chat scrolls. If Streamlit changes its page structure this just
# stops working and the pane scrolls with the page; nothing breaks.
st.markdown("""<style>
div[data-testid="stColumn"]:has(#pdf-pane) { position: sticky; top: 3rem; align-self: flex-start; }
</style>""", unsafe_allow_html=True)

# No profile is named here: boto3 uses your AWS_PROFILE or your login's credentials.
# The region comes from AWS_REGION (which boto3 ignores by itself), AWS_DEFAULT_REGION or your profile.
session = boto3.Session(region_name=os.environ.get("AWS_REGION"))

# Long answers (like a gaps analysis) can take a minute or more. boto3 gives up after 60 seconds by
# default, so wait up to 15 minutes. Retries are off: a retry would run the whole agent a second time.
SLOW_CALL_CONFIG = Config(read_timeout=900, retries={"max_attempts": 1, "mode": "standard"})


@st.cache_resource
def find_agent_arn():
    """Ask AgentCore for the ARN of the agent called AGENT_NAME (so nobody has to copy it by hand)."""
    control = session.client("bedrock-agentcore-control")
    for page in control.get_paginator("list_agent_runtimes").paginate():
        for runtime in page["agentRuntimes"]:
            if runtime["agentRuntimeName"] == AGENT_NAME:
                return runtime["agentRuntimeArn"]
    raise RuntimeError(f"No AgentCore agent named {AGENT_NAME} found. Did terraform apply finish?")


@st.cache_data(ttl=300)
def library_rows():
    """The year and language of every loaded document (empty list if the table can't be read)."""
    try:
        table = session.resource("dynamodb").Table(DOCS_TABLE)
        rows, kwargs = [], {"ProjectionExpression": "#y, #l",
                            "ExpressionAttributeNames": {"#y": "year", "#l": "language"}}
        while True:  # follow pagination
            page = table.scan(**kwargs)
            rows += [{"year": d.get("year", ""), "language": d.get("language", "")} for d in page["Items"]]
            if "LastEvaluatedKey" not in page:
                return rows
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    except Exception:
        return []


def library_caption(language):
    """Say what is searched, e.g. 'Searching 15 WRI publications, 2024.'"""
    rows = [r for r in library_rows() if not language or r["language"] == language]
    if not rows:
        return ""
    years = sorted(r["year"] for r in rows if r["year"])
    span = "" if not years else f", {years[0]}" if years[0] == years[-1] else f", {years[0]}–{years[-1]}"
    kind = f"{LANGUAGES.get(language, language)} " if language else ""
    return f"Searching {len(rows)} {kind}WRI publication{'s' if len(rows) != 1 else ''}{span}."


@st.cache_data(show_spinner=False)
def pdf_bytes(doc_id, _url):
    """Download a source PDF from the temporary link the agent gave us (cached per document).
    The leading underscore tells Streamlit not to include the link in the cache key."""
    response = requests.get(_url, timeout=60)
    response.raise_for_status()
    return response.content


LINK_MAX_AGE = 1200  # seconds: a link older than this (20 minutes) is replaced before use


def fresh_pdf_link(doc_id):
    """Ask the agent for a new temporary link to a document's PDF (fast: no question is answered)."""
    client = session.client("bedrock-agentcore", config=SLOW_CALL_CONFIG)
    resp = client.invoke_agent_runtime(agentRuntimeArn=find_agent_arn(),
                                       runtimeSessionId=st.session_state.session_id,
                                       payload=json.dumps({"action": "pdf_link", "doc_id": doc_id}))
    return json.loads(resp["response"].read()).get("url", "")


def page_label(pages):
    """'26' -> 'p. 26', '2-3' -> 'pp. 2-3'."""
    return f"pp. {pages}" if "-" in pages else f"p. {pages}"


def draw_pane(source):
    """The right-hand pane: the source PDF, with a close button."""
    st.markdown('<div id="pdf-pane"></div>', unsafe_allow_html=True)
    head, close = st.columns([6, 1])
    head.markdown(f"**{source['document']}**  \n{source['section']} · {page_label(source['pages'])}")
    if close.button("✕", key="close_pane", help="Close"):
        st.session_state.viewing = None
        st.rerun()

    url, data, problem = source.get("url", ""), None, None
    for attempt in (1, 2):  # attempt 2 uses a fresh link, for an old or expired one
        try:
            if not url:
                url = fresh_pdf_link(source["doc_id"])
            if not url:
                problem = "The agent could not make a link to this PDF."
                break
            data = pdf_bytes(source["doc_id"], url)
            break
        except Exception as e:
            problem, url = f"{type(e).__name__}: {e}", ""  # forget the link; the next attempt gets a new one
    if data is None:
        st.warning("Couldn't load the PDF.")
        with st.expander("Technical details"):
            st.code(problem)
        return
    try:
        st.pdf(data, height=520)
    except Exception as e:
        st.warning("Couldn't show the PDF here. Is the PDF viewer installed? "
                   "Run: pip install -r requirements.txt")
        with st.expander("Technical details"):
            st.code(f"{type(e).__name__}: {e}")
    first_page = source["pages"].split("-")[0]
    st.link_button(f"Open in a new tab at page {first_page}", f"{url}#page={first_page}")


def draw_sources(message, index):
    """One 'Sources' list, grouped by document. Clicking a section opens its PDF on the right."""
    read = message.get("read") or []
    if not read:
        return
    documents = {}
    for item in read:
        documents.setdefault(item["source"], {"title": item["document"], "sections": []})["sections"].append(item)
    with st.expander(f"Sources ({len(documents)} document{'s' if len(documents) != 1 else ''}, "
                     f"{len(read)} section{'s' if len(read) != 1 else ''})"):
        for number, document in documents.items():
            st.markdown(f"**[{number}] {document['title']}**")
            for k, item in enumerate(document["sections"]):
                label = f"{item['section']} · {page_label(item['pages'])}"
                if st.button(label, key=f"source{index}_{number}_{k}", type="tertiary"):
                    recent = time.time() - message.get("answered_at", 0) < LINK_MAX_AGE
                    st.session_state.viewing = {
                        **item, "url": message.get("pdfs", {}).get(item["doc_id"], "") if recent else ""}
                    st.rerun()


def draw_chart(chart):
    """Draw one chart the agent asked for (bar, barh, line or pie)."""
    labels, series, kind = chart["labels"], chart["series"], chart["chart_type"]
    table = pd.DataFrame(series, index=labels)  # one column per series, one row per label
    long = table.reset_index(names="label").melt("label", var_name="series", value_name="value")
    unit = chart.get("unit") or ""
    colors = alt.Scale(range=PALETTE)
    legend = alt.Legend(title=None) if len(series) > 1 else None
    if kind == "pie":
        first = long[long["series"] == long["series"].iloc[0]]
        picture = alt.Chart(first).mark_arc(innerRadius=50).encode(
            theta="value:Q", color=alt.Color("label:N", sort=None, scale=colors, legend=alt.Legend(title=None)),
            tooltip=["label", "value"])
    elif kind == "line":
        picture = alt.Chart(long).mark_line(point=True).encode(
            x=alt.X("label:N", sort=None, title=None), y=alt.Y("value:Q", title=unit),
            color=alt.Color("series:N", scale=colors, legend=legend), tooltip=["label", "series", "value"])
    elif kind == "barh":
        picture = alt.Chart(long).mark_bar().encode(
            y=alt.Y("label:N", sort=None, title=None), x=alt.X("value:Q", title=unit), yOffset="series:N",
            color=alt.Color("series:N", scale=colors, legend=legend), tooltip=["label", "series", "value"])
    else:  # bar
        picture = alt.Chart(long).mark_bar().encode(
            x=alt.X("label:N", sort=None, title=None), y=alt.Y("value:Q", title=unit), xOffset="series:N",
            color=alt.Color("series:N", scale=colors, legend=legend), tooltip=["label", "series", "value"])
    st.markdown(f"**{chart['title']}**")
    st.altair_chart(picture.configure_view(stroke=None), width="stretch")
    if chart.get("note"):
        st.caption(chart["note"])


def draw_visual(visual):
    """Draw a chart, or a dashboard (number tiles plus a few charts)."""
    if visual["kind"] == "chart":
        draw_chart(visual)
        return
    st.markdown(f"### {visual['title']}")
    for column, kpi in zip(st.columns(len(visual["kpis"])), visual["kpis"]):
        column.metric(kpi["label"], kpi["value"])
    for column, chart in zip(st.columns(len(visual["charts"])), visual["charts"]):
        with column:
            draw_chart(chart)
    st.caption(visual.get("note", ""))


# Plain-English explanations for common errors: (words to look for, what happened, what to do)
ERROR_HELP = [
    (("ExpiredToken", "expired"), "Your AWS login has expired.",
     "Log in again in this terminal, then restart this page."),
    (("AccessDenied", "not authorized"), "Your AWS role isn't allowed to do that.",
     "It needs permission to find and call the agent (bedrock-agentcore)."),
    (("Unable to locate credentials", "NoCredentials", "specify a region"), "AWS isn't set up in this terminal.",
     "Set your AWS login and AWS_DEFAULT_REGION, then restart this page."),
    (("No AgentCore agent named", "ResourceNotFound"), "I couldn't find the AskWRI agent.",
     "Check that terraform apply finished and that you are using the same region."),
    (("RuntimeClientError", "(500)"), "The agent hit an error while answering.",
     "Try again. If it keeps happening, look at the agent's logs in CloudWatch."),
    (("Read timeout", "timed out"), "That took too long.", "Try a narrower question."),
]


def friendly_error(error):
    """Turn an error into a short explanation and a suggestion."""
    text = str(error)
    for words, what, todo in ERROR_HELP:
        if any(word in text for word in words):
            return what, todo
    return "Something went wrong.", "Please try again."


def ask_agent(prompt, session_id, agent_arn, language):
    """Send the prompt to the agent and return its reply (a dict). Runs in a helper thread."""
    request = {"prompt": prompt, "language": language}  # language "" = search every language
    if USE_LOCAL_AGENT:
        return requests.post(LOCAL_URL, json=request, timeout=600).json()
    client = session.client("bedrock-agentcore", config=SLOW_CALL_CONFIG)
    resp = client.invoke_agent_runtime(agentRuntimeArn=agent_arn, runtimeSessionId=session_id,
                                       payload=json.dumps(request))
    return json.loads(resp["response"].read())


# While a source is open, the chat goes in the left column and the PDF in the right one
chat, pane = st.columns([1, 1]) if viewing else (st.container(), None)

with chat:
    st.title("AskWRI")

    # A language choice appears only when the library holds documents in more than one language
    languages = {r["language"] for r in library_rows() if r["language"]}
    language = ""
    if len(languages) > 1:
        names = {LANGUAGES.get(code, code): code for code in sorted(languages)}
        choice = st.selectbox("Search documents in", ["All languages"] + list(names), key="language_choice")
        language = names.get(choice, "")
    st.caption(f"Ask a question, write a research briefing, or find gaps in WRI's research. "
               f"{library_caption(language)}")

    # 1. Set up the session id and chat history on first load
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []

    # 2. Show the earlier messages, each answer with its charts and a Sources list
    for index, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for visual in message.get("visuals", []):
                draw_visual(visual)
            draw_sources(message, index)
            if message.get("documents") == 1:
                st.caption("Single source: every finding comes from one document, so nothing here is "
                           "cross-checked against other WRI publications.")

    # 3. Buttons: examples on an empty chat, suggested follow-ups under the latest answer
    if not st.session_state.messages:
        for example in EXAMPLES:
            if st.button(example, width="stretch"):
                st.session_state.queued = example
                st.rerun()
    elif st.session_state.messages[-1]["role"] == "assistant":
        suggestions = st.session_state.messages[-1].get("followups", [])
        for number, suggestion in enumerate(suggestions):
            if st.button(suggestion, key=f"suggestion{number}", width="stretch"):
                st.session_state.queued = suggestion
                st.rerun()
        if not suggestions:  # no suggestions from the agent: offer the two standard follow-ups
            for column, label in zip(st.columns(len(FOLLOW_UPS)), FOLLOW_UPS):
                if column.button(label):
                    st.session_state.queued = FOLLOW_UPS[label]
                    st.rerun()

    # 4. Handle a new question (typed, or queued by a button)
    typed = st.chat_input("Ask a question, request a briefing, or find research gaps")
    user_text = st.session_state.pop("queued", None) or typed
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)
        with st.chat_message("assistant"):
            reply, error = None, None
            with st.status("Searching WRI research...") as status:
                started = time.time()
                try:
                    arn = None if USE_LOCAL_AGENT else find_agent_arn()
                    # Ask in a helper thread so this page can show a running timer meanwhile
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(ask_agent, user_text, st.session_state.session_id, arn, language)
                        while not future.done():
                            status.update(label=f"Searching WRI research... {int(time.time() - started)}s")
                            time.sleep(1)
                        reply = future.result()
                    status.update(label=f"Done in {int(time.time() - started)}s", state="complete")
                except Exception as e:  # show a friendly message instead of a long traceback
                    error = e
                    status.update(label="Something went wrong", state="error")
            if error:
                what, todo = friendly_error(error)
                st.error(f"{what} {todo}")
                with st.expander("Technical details"):
                    st.code(str(error))
                st.stop()
        st.session_state.messages.append({
            "role": "assistant", "content": reply["answer"],
            "documents": reply.get("documents", 0), "sections": reply.get("sections", 0),
            "visuals": reply.get("visuals", []), "followups": reply.get("followups", []),
            "read": reply.get("read", []), "pdfs": reply.get("pdfs", {}), "answered_at": time.time()})
        st.rerun()  # redraw from the history, so the answer shows its sources and follow-up buttons

if pane is not None:
    with pane:
        draw_pane(viewing)

"""The AskWRI chat page. Sends each question to the agent (local or on AgentCore)
and shows the answer with its citations.
"""
import json
import os
import re
import time
import uuid

import boto3
import requests
import streamlit as st
from botocore.config import Config

# Replace account_id with your AWS account id (or set the AGENT_ARN environment variable).
# Set it to "" to use the local agent.
AGENT_ARN = os.environ.get("AGENT_ARN", "arn:aws:bedrock-agentcore:us-east-1:account_id:runtime/askwri_agent-wPm1MF2o63")
LOCAL_URL = "http://localhost:8080/invocations"
REGION = "us-east-1"
DOCS_TABLE = "askwri-documents"

# One sample per thing the agent can do, shown as buttons in the sidebar
EXAMPLES = [
    ("Ask a question", "What does WRI say about food loss and waste in Kenya?"),
    ("Write a briefing", "Write a short research briefing on electric school buses."),
    ("Find research gaps", "Where are the gaps in WRI's research on energy efficiency?"),
]

# The agent ends every answer with a "## Sources" heading; everything after it is the source list
SOURCES_RE = re.compile(r"\n#{1,4}\s*\**Sources\**\s*\n", re.IGNORECASE)


@st.cache_resource
def agent_client():
    # Gap analyses and briefings can take close to a minute; the boto3 default read timeout is 60 s.
    # No automatic retry, so a slow question is never run (and paid for) twice.
    config = Config(read_timeout=900, connect_timeout=10, retries={"max_attempts": 1})
    return boto3.Session(region_name=REGION).client("bedrock-agentcore", config=config)


@st.cache_data(ttl=600)
def library_stats():
    """Return (number of documents, first year, last year), or None if the table can't be read."""
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
        years = sorted(i["year"] for i in items if i.get("year"))
        return len(items), years[0], years[-1]
    except Exception:
        return None


def ask_agent(user_text):
    """Send the question to the agent and return its answer text."""
    if not AGENT_ARN:
        return requests.post(LOCAL_URL, json={"prompt": user_text}, timeout=900).json()["answer"]
    resp = agent_client().invoke_agent_runtime(agentRuntimeArn=AGENT_ARN,
                                               runtimeSessionId=st.session_state.session_id,
                                               payload=json.dumps({"prompt": user_text}))
    return json.loads(resp["response"].read())["answer"]


def show_answer(text, seconds=None):
    """Show the answer, with the source list folded into an expander."""
    body, *rest = SOURCES_RE.split("\n" + text, maxsplit=1)
    st.markdown(body.strip())
    if rest:
        documents = len(re.findall(r"^\s*[-*]\s+\*\*", rest[0], re.MULTILINE))
        label = f"Sources ({documents} documents)" if documents else "Sources"
        with st.expander(label, expanded="## Briefing" in "\n" + body):  # briefings show document details open
            st.markdown(rest[0].strip())
    if seconds:
        st.caption(f"Answered in {seconds} s")


st.set_page_config(page_title="AskWRI", page_icon="🌍")
st.title("AskWRI")

stats = library_stats()
if stats:
    st.caption(f"Searching {stats[0]} WRI research publications ({stats[1]}–{stats[2]}). "
               "Answers are limited to these documents, not all of WRI's work.")

# 1. Set up the session id and chat history on first load
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

# 2. Sidebar: example questions and a reset button
with st.sidebar:
    st.header("Try one")
    for label, example in EXAMPLES:
        if st.button(label, use_container_width=True, help=example):
            st.session_state.pending = example
    st.divider()
    if st.button("New conversation", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# 3. Show the earlier messages (or a short guide when the chat is empty)
if not st.session_state.messages:
    st.markdown("**Ask a question.** Every answer cites the document, pages and a quoted passage.  \n"
                "**Write a briefing.** Try \"Write a briefing on …\".  \n"
                "**Find research gaps.** Try \"Where are the gaps in WRI's research on …?\"")
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            show_answer(message["content"], message.get("seconds"))
        else:
            st.markdown(message["content"])

# 4. Handle a new question (typed, or from a sidebar button)
user_text = st.chat_input("Ask about WRI research") or st.session_state.pop("pending", None)
if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)
    with st.chat_message("assistant"):
        status = st.status("Searching and reading WRI documents. This can take up to a minute.")
        started = time.time()
        try:
            answer = ask_agent(user_text)
        except Exception as error:
            status.update(label="Something went wrong", state="error")
            st.error(f"The agent did not answer ({type(error).__name__}). Please try again.")
            st.session_state.messages.pop()  # drop the unanswered question so history stays in pairs
            st.stop()
        seconds = round(time.time() - started)
        status.update(label=f"Done in {seconds} s", state="complete")
        show_answer(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer, "seconds": seconds})

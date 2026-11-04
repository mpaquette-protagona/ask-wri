"""The AskWRI chat page. Sends each question to the agent (local or on AgentCore)
and shows the answer with its citations.
"""
import json
import uuid

import boto3
import requests
import streamlit as st

AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:615758710841:runtime/askwri_agent-jCYQj2FUOI"  # set to "" to use the local agent
LOCAL_URL = "http://localhost:8080/invocations"


def ask_agent(user_text):
    """Send the question to the agent and return its answer text."""
    if not AGENT_ARN:
        return requests.post(LOCAL_URL, json={"prompt": user_text}, timeout=600).json()["answer"]
    client = boto3.Session(profile_name="builder", region_name="us-east-1").client("bedrock-agentcore")
    resp = client.invoke_agent_runtime(agentRuntimeArn=AGENT_ARN,
                                       runtimeSessionId=st.session_state.session_id,
                                       payload=json.dumps({"prompt": user_text}))
    return json.loads(resp["response"].read())["answer"]


st.title("AskWRI")

# 1. Set up the session id and chat history on first load
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

# 2. Show the earlier messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 3. Handle a new question
user_text = st.chat_input("Ask about WRI research")
if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)
    with st.chat_message("assistant"):
        with st.spinner("Searching WRI research..."):
            answer = ask_agent(user_text)
        st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})

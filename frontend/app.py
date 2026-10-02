"""Minimal Streamlit chat UI. It only calls the backend's POST /chat."""
import os
import uuid

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Weather Advisory Bot")
st.title("Weather Advisory Bot")
st.caption('Ask about outdoor safety, e.g. "Is it safe to cycle to work in Bhopal today?"')

# New session on every page load; the backend keeps the memory per session_id.
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        (st.text if m["role"] == "assistant" else st.markdown)(m["text"])
        if m.get("meta"):
            st.caption(m["meta"])

if message := st.chat_input("Type a question..."):
    st.session_state.messages.append({"role": "user", "text": message})
    with st.chat_message("user"):
        st.markdown(message)
    with st.chat_message("assistant"):
        with st.spinner("Checking live weather and SOPs..."):
            try:
                r = requests.post(f"{BACKEND_URL}/chat", timeout=90,
                                  json={"session_id": st.session_state.session_id, "message": message})
                r.raise_for_status()
                data = r.json()
                text = data["reply"]
                meta = f"path: {data['path']} · SOPs: {', '.join(data['sop_ids']) or 'none'}"
            except requests.RequestException as e:
                text, meta = f"Sorry, the backend returned an error: {e}", None
        st.text(text)  # plain text keeps the SOP wording and line breaks exactly as written
        if meta:
            st.caption(meta)
    st.session_state.messages.append({"role": "assistant", "text": text, "meta": meta})

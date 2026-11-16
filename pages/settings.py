import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import re

import streamlit as st

from database import db_manager as db
from modules import state, ui, ai_engine as AI
from modules.fiverr_mcp import FiverrMCPClient, MCPError, DEFAULT_URL, READ_ONLY_TOOLS

ui.setup("Settings", "Connection, AI provider and data management. Secrets are never shown or stored in the browser.", "⚙️")
state.bootstrap()
st.subheader("Fiverr account")
u = st.text_input("Fiverr username", st.session_state.get("username", ""), max_chars=40)
live = st.toggle("Try the live Fiverr MCP first (falls back to the offline snapshot)", st.session_state.get("prefer_live", True))
if st.button("Save & reload", type="primary"):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{2,40}", u.strip().split("/")[-1]):
        st.error("Usernames contain letters, numbers, underscores and hyphens only.")
    else:
        st.session_state["username"], st.session_state["prefer_live"] = u.strip().split("/")[-1], live
        state.refresh()
        st.rerun()
st.caption(f"MCP endpoint: `{DEFAULT_URL}` (override with FIVERR_MCP_URL). Mode: **read-only** — allowed tools: {', '.join(sorted(READ_ONLY_TOOLS))}. This app cannot modify a live gig.")
if st.button("List tools exposed by the Fiverr MCP (live)"):
    try:
        for t in FiverrMCPClient().list_tools():
            st.markdown(f"- `{t['name']}` — {t.get('description', '')[:140]}")
    except MCPError as e:
        st.error(str(e))
st.subheader("AI provider")
p = AI.provider()
st.write(f"Provider: **{p['provider']}** · model: `{p['model']}` · API key: **{'configured ✅' if AI.llm_available() else 'not set — rule-based fallback active'}**")
st.markdown("Configure with environment variables or Streamlit secrets: `LLM_PROVIDER` (`openai` | `anthropic`), `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, optional `LLM_MODEL`, `OPENAI_BASE_URL`. See README.")
st.subheader("Data")
st.write(f"SQLite file: `{db.DB_PATH}` — on Streamlit Community Cloud this storage is **ephemeral**; export reports you want to keep.")
c1, c2 = st.columns(2)
if c1.button("Clear imported analytics"):
    db.clear_perf()
    st.success("Cleared.")
if c2.button("Clear Fiverr data cache"):
    state.refresh()
    st.success("Cache cleared.")
st.subheader("Safety")
st.markdown("- Read-only by design; any future write action must be added explicitly and gated by a confirmation dialog.\n- No Fiverr password or API credentials are requested.\n"
            "- No scraping of Fiverr search; rankings are manual observations.\n- Inputs are length-limited and validated; errors never echo secrets.")

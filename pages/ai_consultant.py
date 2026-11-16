import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st

from database import db_manager as db
from modules import state, ui, ai_engine as AI, strategy_engine as S, analytics_engine as AE, ranking_engine as RE

ui.setup("AI Business Consultant", "Ask about your gigs. Answers separate [VERIFIED] facts, [ESTIMATE]s and [RECOMMENDATION]s, and name missing data.", "🤖")
acct = state.bootstrap()
if acct:
    au = state.audits(acct)
    perf = state.perf_df()
    comp = st.session_state.get("comp_summary")
    diag = []
    perf_summary = None
    if perf is not None:
        s = AE.summarize(perf)
        perf_summary = {k: (None if str(v) == "nan" else v) for k, v in s.items() if k not in ("start", "end")}
        for g_ in perf["gig"].unique():
            diag += AE.diagnose(perf[perf["gig"] == g_], perf)
    rank = RE.summarize(db.rank_df())
    ctx = AI.build_context(acct, au, perf_summary, comp, rank)
    objs = {"account": acct, "audits": au, "perf": perf, "comp": comp, "diagnoses": diag}
    st.caption(("🟢 LLM connected" if AI.llm_available() else "⚪ No LLM key — using the rule-based consultant (set an API key in Settings for open-ended answers)") + " · grounded in your Fiverr data, audits, imports and research")
    qs = ["Why are my Fiverr impressions decreasing?", "Why do I get clicks but no orders?", "Which gig should I optimize first?", "Which keywords should I target?",
          "Which competitor has better positioning?", "Which new gig should I create?", "How can I improve my Fiverr business over the next 90 days?"]
    cols = st.columns(3)
    picked = None
    for i, q in enumerate(qs):
        if cols[i % 3].button(q, key=f"q{i}", width="stretch"):
            picked = q
    for m in st.session_state["chat"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    q = st.chat_input("Ask about your Fiverr business…", max_chars=600) or picked
    if q:
        st.session_state["chat"].append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        hist = [{"role": m["role"], "content": m["content"]} for m in st.session_state["chat"][-7:-1]]
        ans, eng = AI.consultant_answer(q, ctx, objs, hist)
        with st.chat_message("assistant"):
            st.markdown(ans)
            st.caption(f"Engine: {eng}")
        st.session_state["chat"].append({"role": "assistant", "content": ans})
    if st.session_state["chat"] and st.button("Clear conversation"):
        st.session_state["chat"] = []
        st.rerun()

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st

from database import db_manager as db
from modules import state, ui, ai_engine as AI

ui.setup("Description Optimizer", "Rewrites a description around the buyer's problem using only facts found in your data. Nothing is published.", "📝")
acct = state.bootstrap()
if acct:
    g = state.pick_gig(acct, "do_gig")
    meta = db.get_meta(g["slug"])
    use_llm = st.toggle("Use LLM if configured", value=True)
    if st.button("Optimize description", type="primary"):
        st.session_state["desc_opt"] = (g["slug"], AI.optimize_description(g, acct, meta, use_llm))
    cur = st.session_state.get("desc_opt")
    if cur and cur[0] == g["slug"]:
        r = cur[1]
        st.markdown(f"Engine: `{r['engine']}` · keyword: **{r['keyword']}**")
        if not r["engine"].startswith("LLM"):
            st.info("Rule-based draft: structure and claims are safe, wording is generic. Review every line; connect an LLM key (Settings) for more natural copy.")
        a, b = st.columns(2)
        with a:
            st.subheader("Original")
            st.text_area("orig", r["original"], height=420, label_visibility="collapsed", disabled=True)
            st.caption(f"{r['before']['chars']} characters")
        with b:
            st.subheader("Improved")
            new = st.text_area("improved", r["improved"], height=420, label_visibility="collapsed")
            st.caption(f"{len(new)} characters · limit {AI.DESC_LIMIT}")
            st.code(new, language=None)
        c = st.columns(4)
        ui.kpi(c[0], "Description score before", f"{r['before']['score']}/{r['before']['max']}")
        ui.kpi(c[1], "After (rule-checked)", f"{r['after']['score']}/{r['after']['max']}", f"{r['after']['score'] - r['before']['score']:+.1f}")
        ui.kpi(c[2], "Keyword mentions", f"{r['before']['kw']} → {r['after']['kw']}")
        ui.kpi(c[3], "Length", f"{r['before']['chars']} → {r['after']['chars']}")
        st.subheader("What changed and why")
        for ch in r["changes"]:
            st.markdown(f"- {ch}")
        st.warning("Verify every claim (ratings, years, turnaround) is true before pasting into Fiverr. Scores are internal, not Fiverr metrics.")

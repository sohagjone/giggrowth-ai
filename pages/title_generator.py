import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st

from database import db_manager as db
from modules import state, ui, ai_engine as AI

ui.setup("AI Title Generator", "10 ranked title options. Nothing is published — copy the one you like into your gig editor.", "✍️")
acct = state.bootstrap()
if acct:
    g = state.pick_gig(acct, "tg_gig")
    meta = db.get_meta(g["slug"])
    st.caption(f"Current title used: **{meta.get('title') or g['derived_title']}** " + ("" if meta.get("title") else "(derived from URL slug — enter the exact title in Gig SEO Audit › Gig metadata)"))
    use_llm = st.toggle("Use LLM if configured", value=True, help="Falls back to transparent rule-based generation without an API key.")
    if st.button("Generate 10 titles", type="primary"):
        rows, engine = AI.generate_titles(g, acct, meta, 10, use_llm)
        st.session_state["titles"] = (g["slug"], rows, engine)
    cur = st.session_state.get("titles")
    if cur and cur[0] == g["slug"]:
        _, rows, engine = cur
        st.markdown(f"Engine: `{engine}`" + ("" if "LLM" in engine else " — rule-based drafts; connect an LLM key in Settings for more natural variety."))
        st.caption(f"Rule: text after “I will” must be ≤ {AI.TITLE_LIMIT} characters (verify the current limit in Fiverr's gig editor). Ranked by internal title score, length fit and specificity.")
        for i, r in enumerate(rows, 1):
            with st.container(border=True):
                a, b = st.columns([5, 1])
                a.markdown(f"**{i}.** {r['why']}")
                a.code(r["full"], language=None)
                b.metric("Title score", f"{r['score']}/20")
                b.caption(f"{r['chars']}/{AI.TITLE_LIMIT} chars")

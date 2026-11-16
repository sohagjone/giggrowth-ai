import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st

from modules import state, ui, keyword_engine as K, report_generator as R

ui.setup("Keyword Research", "Candidate keywords from your service or gig URL. **No Fiverr search volumes exist here — opportunity is a qualitative assessment.**", "🔑")
acct = state.bootstrap()
if acct:
    ui.source_banner(acct)
    c1, c2 = st.columns([3, 2])
    preset = c2.selectbox("Example services", [""] + K.PRESET_SERVICES)
    text = c1.text_input("Service name or Fiverr gig URL", preset or "", placeholder="e.g. n8n workflow automation  or  https://www.fiverr.com/you/your-gig", max_chars=200)
    use_gig = st.checkbox("Use one of my gigs as context (improves relevance scoring)")
    ctx = ""
    if use_gig:
        g = state.pick_gig(acct, "kw_gig")
        ctx = g["derived_title"] + " " + g["description"]
        text = text or g["url"]
    comp = st.session_state.get("competitors")
    corpus = [(s.get("oneLinerTitle") or "") + " " + " ".join(s.get("skills") or []) for s in (comp["sellers"] if comp else [])]
    st.caption(f"Competition evidence: {len(corpus)} competitor profiles loaded." if corpus else "Competition evidence: none loaded — run **Competitor Intelligence** first to add it.")
    if st.button("Research keywords", type="primary", disabled=not text.strip()):
        st.session_state["kw_df"] = K.generate(text, ctx, corpus)
        st.session_state["kw_src"] = text
    df = st.session_state.get("kw_df")
    if df is not None and not df.empty:
        f1, f2, f3 = st.columns(3)
        types = f1.multiselect("Type", sorted(df["Type"].unique()), default=sorted(df["Type"].unique()))
        opps = f2.multiselect("Opportunity", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
        q = f3.text_input("Contains")
        v = df[df["Type"].isin(types) & df["Opportunity (qualitative)"].isin(opps) & df["Keyword"].str.contains(q, case=False, regex=False)]
        st.dataframe(v, width="stretch", hide_index=True)
        st.caption("Keywords are template-generated candidates, not observed searches. Validate by typing them into Fiverr's search box and reading the suggestions and competing gigs.")
        st.download_button("⬇️ Download keyword research (Excel)", R.keywords_xlsx(df, f"Input: {st.session_state.get('kw_src')}"), "keyword_research.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    elif df is not None:
        st.info("No keywords generated.")

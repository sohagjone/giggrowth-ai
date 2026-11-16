import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import streamlit as st

from modules import state, ui, strategy_engine as S

ui.setup("Gig Health Monitor", "Internal status per gig. Components without data are listed as missing — never assumed.", "🩺")
acct = state.bootstrap()
if acct:
    ui.source_banner(acct)
    au = state.audits(acct)
    perf = state.perf_df()
    comp = st.session_state.get("comp_summary")
    color = {"Excellent": "🟢", "Good": "🟢", "Needs Improvement": "🟠", "Poor": "🔴"}
    rows = []
    res = {}
    for a, g in zip(au, acct["gigs"]):
        pg = None
        if perf is not None:
            m = perf[perf["gig"].str.contains(g["slug"].split("-")[0], case=False, regex=False)] if perf["gig"].nunique() > 1 else perf
            pg = m if not m.empty else None
        h = S.health(a, acct, pg, comp, g)
        res[g["slug"]] = h
        rows.append({"Gig": g["slug"], "Status": f"{color[h['status']]} {h['status']}", "Health score": h["score"], "Data coverage": f"{h['data_coverage']:.0%}"})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    st.caption("Status bands (internal): Excellent ≥ 80 · Good 65–79 · Needs Improvement 45–64 · Poor < 45. Weights: SEO 30, feedback 20, impressions/CTR/conversion trends 15 each, competitive position 5; unknown components are excluded.")
    for slug, h in res.items():
        with st.expander(f"{color[h['status']]} {slug} — {h['status']} ({h['score']})"):
            st.markdown("**Why this status**")
            for n, sc, w, why in h["components"]:
                st.markdown(f"- **{n}** — {sc:.0f}/100 (weight {w}): {why}")
            if h["missing"]:
                st.markdown("**Missing information**")
                for m in h["missing"]:
                    st.markdown(f"- {ui.badge('Data limit', 'MISSING')} {m}", unsafe_allow_html=True)

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import streamlit as st

from modules import state, ui, strategy_engine as S, report_generator as R

ui.setup("Growth Strategy", "Prioritised 7 / 30 / 60 / 90-day plans from your actual data. No outcome is guaranteed.", "🚀")
acct = state.bootstrap()
if acct:
    ui.source_banner(acct)
    au = state.audits(acct)
    perf = state.perf_df()
    comp = st.session_state.get("comp_summary")
    plans = S.build_plans(acct, au, perf, comp)
    fnd = S.findings(acct, au)
    st.subheader("Situation")
    for f in fnd:
        st.markdown(f"{ui.badge(f['type'])} {f['text']}", unsafe_allow_html=True)
    if perf is None:
        st.warning("No analytics imported: visibility, click and conversion recommendations below are based on on-page audit and reviews only.")
    st.subheader("Plans")
    tabs = st.tabs(["7-day action plan", "30-day growth plan", "60-day optimization plan", "90-day business development plan"])
    for t, d in zip(tabs, [7, 30, 60, 90]):
        with t:
            df = pd.DataFrame(plans[d])
            st.dataframe(df.drop(columns=["Priority score"]), width="stretch", hide_index=True)
    st.caption("Priority = impact × evidence ÷ effort. Evidence: Verified = found in your data · Estimate = inferred · Hypothesis = test it before committing.")
    st.subheader("Strategy by lever")
    lev = {"Visibility": ["Visibility", "Positioning", "Data"], "Clicks": ["Click growth", "Click & conversion"], "Conversion": ["Conversion", "Pricing", "Trust", "Trust / compliance"], "Business growth": ["Business growth", "Measurement"]}
    allp = pd.DataFrame([dict(r, Plan=f"{d}-day") for d, rs in plans.items() for r in rs])
    cols = st.columns(4)
    for col, (name, areas) in zip(cols, lev.items()):
        with col:
            st.markdown(f"**{name}**")
            for _, r in allp[allp["Area"].isin(areas)].head(5).iterrows():
                st.markdown(f"- {r['Action']} _({r['Plan']})_")
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Growth strategy (PDF)", R.strategy_pdf(acct, au, fnd, plans), "gig_growth_strategy.pdf", "application/pdf")
    c2.download_button("⬇️ 30/60/90-day action plan (PDF)", R.plan_pdf(acct, plans), "action_plan_30_60_90.pdf", "application/pdf")

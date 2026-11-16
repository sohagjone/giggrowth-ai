import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import plotly.express as px
import streamlit as st

from modules import state, ui, strategy_engine as S
from modules.seo_engine import score_band
from modules.fiverr_mcp import days_since

ui.setup("Dashboard", "Your Fiverr portfolio at a glance — real data from the Fiverr MCP, with every gap disclosed.", "📊")
acct = state.bootstrap()
if acct:
    ui.source_banner(acct)
    au = state.audits(acct)
    p = acct["profile"]
    c = st.columns(5)
    avg = sum(a["total"] for a in au) / len(au)
    latest = max((r["date"] for r in acct["reviews"]), default="")
    ui.kpi(c[0], "Published gigs", len(acct["gigs"]), "Only published gigs are returned by the MCP; inactive/draft gigs are Not Available.")
    ui.kpi(c[1], "Avg internal SEO score", f"{avg:.0f}/100", "Internal audit score — not a Fiverr metric.")
    ui.kpi(c[2], "Seller rating", f"{p['rating']['score']} ★", f"{p['rating']['count']} reviews")
    ui.kpi(c[3], "Total reviews", p["rating"]["count"])
    ui.kpi(c[4], "Newest review", f"{days_since(latest)} days ago" if latest else "n/a", latest)
    perf = state.perf_df()
    st.subheader("Gig SEO scores (internal audit)")
    df = pd.DataFrame({"Gig": [a["slug"] for a in au], "Score": [a["total"] for a in au], "Projected": [a["projected"] for a in au],
                       "Band": [score_band(a["total"]) for a in au], "Confidence": [f"{a['confidence']:.0%}" for a in au]})
    fig = px.bar(df.sort_values("Score"), x="Score", y="Gig", orientation="h", color="Band", range_x=[0, 100], template="plotly_white",
                 color_discrete_map={"Excellent": "#0B6E4F", "Good": "#5BB88F", "Needs Improvement": "#F2B134", "Poor": "#D9534F"})
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), yaxis_title=None)
    st.plotly_chart(fig, width="stretch")
    st.caption("Scores reflect on-page quality only. 'Confidence' = share of checks verifiable from MCP data; add title/tags/category in Gig SEO Audit to raise it.")
    left, right = st.columns([3, 2])
    with left:
        st.subheader("What the data says")
        for f in S.findings(acct, au):
            st.markdown(f"{ui.badge(f['type'])} {f['text']}", unsafe_allow_html=True)
    with right:
        st.subheader("Performance data")
        if perf is None:
            ui.not_available("Impressions, clicks, CTR, orders, revenue", "The Fiverr MCP doesn't expose them. Import your analytics export on **Performance Analytics**.")
        else:
            st.success(f"{len(perf):,} daily rows imported ({perf['date'].min():%Y-%m-%d} → {perf['date'].max():%Y-%m-%d}).")
        st.subheader("Top priorities")
        for r in S.build_plans(acct, au, perf)[7][:4]:
            st.markdown(f"- {r['Action']}")

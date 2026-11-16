import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import plotly.express as px
import streamlit as st

from modules import state, ui
from modules.fiverr_mcp import CAPABILITY_MATRIX

ui.setup("My Fiverr Account", "Seller profile, gigs and reviews retrieved through the Fiverr MCP.", "👤")
acct = state.bootstrap()
if acct:
    ui.source_banner(acct)
    if st.button("🔄 Refresh from Fiverr", help="Re-query the Fiverr MCP (cached for 15 minutes otherwise)."):
        state.refresh()
        st.rerun()
    p = acct["profile"]
    c1, c2 = st.columns([1, 3])
    with c1:
        if p.get("avatar_url"):
            st.image(p["avatar_url"], width=140)
    with c2:
        st.subheader(f"{p['display_name']} · @{acct['username']}")
        st.write(p["title"])
        st.caption(f"{p.get('country')} · Languages: " + ", ".join(f"{l['code']} ({l['level'].replace('_', ' ').title()})" for l in p.get("languages", [])))
        st.write(p["description"])
    c = st.columns(4)
    s = acct["reviews_summary"]
    ui.kpi(c[0], "Rating", p["rating"]["score"])
    ui.kpi(c[1], "Reviews", p["rating"]["count"])
    ui.kpi(c[2], "Communication", f"{s['communication']:.2f}" if s.get("communication") else "n/a")
    ui.kpi(c[3], "Starting price", f"${float(p['starting_price']['amount']):.0f}" if p.get("starting_price") else "n/a")
    st.markdown("**Not available through the MCP:** total orders, earnings, active vs inactive gig counts, seller level, response/delivery performance beyond what's shown. "
                "Import analytics for orders/earnings.")
    st.subheader("Published gigs")
    rows = [{"Gig (title derived from URL)": g["derived_title"], "Basic $": g["packages"][0]["price"], "Standard $": g["packages"][1]["price"] if len(g["packages"]) > 1 else None,
             "Premium $": g["packages"][-1]["price"], "Description chars": len(g["description"]), "URL": g["url"]} for g in acct["gigs"]]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, column_config={"URL": st.column_config.LinkColumn("URL")})
    st.subheader("Reviews")
    rv = pd.DataFrame(acct["reviews"])
    if not rv.empty:
        rv["year"] = rv["date"].str[:4]
        a, b = st.columns(2)
        with a:
            f = px.histogram(rv, x="year", color=rv["score"].apply(lambda x: "≥4.5" if x >= 4.5 else ("3.5–4.4" if x >= 3.5 else "<3.5")), template="plotly_white", title="Reviews per year (loaded sample)")
            f.update_layout(height=300, legend_title="Score", margin=dict(t=40, b=0))
            st.plotly_chart(f, width="stretch")
        with b:
            st.markdown(f"Loaded **{len(rv)}** of **{p['rating']['count']}** reviews (newest first).")
            low = rv[rv["score"] <= 3.7]
            st.markdown(f"Reviews scoring ≤ 3.7: **{len(low)}**")
            st.dataframe(low[["date", "score", "text"]], width="stretch", hide_index=True)
    st.subheader("What this connection can and cannot provide")
    st.dataframe(pd.DataFrame(CAPABILITY_MATRIX, columns=["Data", "Available via MCP", "Tool / how to get it"]).assign(**{"Available via MCP": lambda d: d["Available via MCP"].map({True: "✅ Yes", False: "❌ No"})}),
                 width="stretch", hide_index=True)

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import streamlit as st

from modules import state, ui, competitor_engine as CE, report_generator as R

ui.setup("Competitor Intelligence", "Public seller and gig data from the Fiverr MCP. Competitor tags and private analytics are not available.", "🏁")
acct = state.bootstrap()
if acct:
    ui.source_banner(acct)
    kw = st.text_input("Service keyword to benchmark", "n8n workflow automation", max_chars=100)
    c1, c2 = st.columns(2)
    live = c1.button("🔎 Search competitors (live, 3 searches)", type="primary")
    snap = c2.button("Use saved competitor snapshot", disabled=not acct.get("competitor_sellers_snapshot"))
    if live:
        with st.spinner("Querying Fiverr MCP…"):
            sellers, errs = CE.discover(kw)
        if sellers:
            st.session_state["competitors"] = {"sellers": sellers, "gigs": {}, "source": "live", "kw": kw}
        for e in errs:
            st.error(e)
        if not sellers and not errs:
            st.info("No sellers returned.")
        if errs and acct.get("competitor_sellers_snapshot"):
            st.info("Live search unavailable — use the saved snapshot button to continue with real data captured earlier.")
    if snap:
        st.session_state["competitors"] = {"sellers": acct["competitor_sellers_snapshot"], "gigs": {}, "source": "snapshot", "kw": "n8n workflow automation developer to extract data from PDF invoices into Google Sheets"}
    comp = st.session_state.get("competitors")
    if not comp:
        ui.not_available("Competitor data", "Run a search or load the snapshot.")
    else:
        sellers = comp["sellers"]
        st.markdown(f"<span class='gg-badge {'gg-live' if comp['source'] == 'live' else 'gg-snap'}'>{comp['source'].upper()}</span> {len(sellers)} competitor sellers for “{comp['kw']}”", unsafe_allow_html=True)
        if st.button("Also fetch their published gigs & prices (1 call per seller)"):
            with st.spinner("Fetching gigs…"):
                g, errs = CE.fetch_gigs([s["username"] for s in sellers])
            comp["gigs"] = g
            for e in errs[:3]:
                st.warning(e)
        a = CE.analyse(acct, sellers, comp.get("gigs") or None)
        st.session_state["comp_summary"] = a
        sdf = CE.sellers_df(sellers)
        st.dataframe(sdf, width="stretch", hide_index=True, column_config={"URL": st.column_config.LinkColumn("URL")})
        gdf = CE.gigs_df(comp["gigs"]) if comp.get("gigs") else pd.DataFrame()
        if not gdf.empty:
            st.subheader("Competitor gigs & prices")
            st.dataframe(gdf, width="stretch", hide_index=True, column_config={"URL": st.column_config.LinkColumn("URL")})
        l, r = st.columns(2)
        with l:
            st.subheader("Most-listed competitor skills")
            st.dataframe(pd.DataFrame(a["top_skills"], columns=["Skill", "Sellers listing it"]), width="stretch", hide_index=True)
        with r:
            st.subheader("Skills they list that your copy doesn't")
            st.dataframe(pd.DataFrame(a["skill_gaps"], columns=["Skill", "Sellers listing it"]), width="stretch", hide_index=True)
        st.subheader("Insights")
        ins = CE.insights(acct, a)
        for i in ins:
            st.markdown(f"{ui.badge(i['type'])} {i['text']}", unsafe_allow_html=True)
        st.caption("Compared on seller level: the MCP returns sellers (skills, headline, rating, order counts), not ranked gig result pages. It cannot show who ranks ahead of you in search.")
        st.download_button("⬇️ Download competitor analysis (Excel)", R.competitors_xlsx(sdf, gdf, ins, f"Fiverr MCP ({comp['source']})"), "competitor_analysis.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

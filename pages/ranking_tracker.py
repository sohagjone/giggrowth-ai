import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plotly.express as px
import streamlit as st
from datetime import datetime

from database import db_manager as db
from modules import state, ui, ranking_engine as RE

ui.setup("Search Position Tracker", "Log what you actually observe in Fiverr search. **Manual observations are not an official Fiverr ranking metric.**", "📍")
acct = state.bootstrap()
if acct:
    st.warning("Fiverr search is personalised, rate-limited and bot-protected. This app does **not** scrape it or bypass CAPTCHA/login. Search in your own browser, "
               "then record the position here. If you can't find the gig, leave the position blank — it's stored as **Not Available**, never guessed.")
    with st.form("obs"):
        c1, c2 = st.columns(2)
        slugs = [g["slug"] for g in acct["gigs"]]
        gig = c1.selectbox("Gig", slugs, format_func=lambda x: x.replace("-", " ")[:70])
        kw = c2.text_input("Target keyword", max_chars=100)
        c3, c4, c5 = st.columns(3)
        pos = c3.number_input("Observed position (0 = not found)", 0, 1000, 0)
        page = c4.number_input("Search page (0 = n/a)", 0, 100, 0)
        cat = c5.text_input("Fiverr category filter", max_chars=80)
        c6, c7 = st.columns(2)
        loc = c6.text_input("Search location / seller-country filter", max_chars=60)
        when = c7.text_input("Date & time (blank = now)", placeholder="2026-11-14 18:30", max_chars=20)
        ctx = st.text_input("Search context (logged in? filters? device?)", max_chars=200)
        ahead = st.text_area("Competitor gigs ranking ahead (usernames/URLs)", max_chars=500)
        if st.form_submit_button("Save observation", type="primary"):
            errs = RE.validate(kw, gig, pos or None, page or None)
            try:
                w = datetime.strptime(when, "%Y-%m-%d %H:%M") if when.strip() else None
            except ValueError:
                w, errs = None, errs + ["Date must look like 2026-11-14 18:30."]
            if errs:
                st.error(" ".join(errs))
            else:
                db.add_rank_obs(RE.make_row(gig, kw, pos or None, page or None, cat, loc, ctx, ahead, w))
                st.success("Observation saved.")
    if kw.strip():
        st.link_button("Open this search on Fiverr ↗", RE.search_url(kw))
    df = db.rank_df()
    if df.empty:
        ui.not_available("Search position history", "No observations logged yet.")
    else:
        st.subheader("Keyword visibility summary")
        st.dataframe(RE.summarize(df), width="stretch", hide_index=True)
        st.subheader("Position history")
        d = df.copy()
        d["position_plot"] = d["position"]
        d["series"] = d["gig_slug"].str[:30] + " | " + d["keyword"]
        fig = px.line(d.dropna(subset=["position"]), x="observed_at", y="position_plot", color="series", markers=True, template="plotly_white")
        fig.update_yaxes(autorange="reversed", title="Position (lower is better)")
        st.plotly_chart(fig, width="stretch")
        nf = d[d["position"].isna()]
        if len(nf):
            st.caption(f"{len(nf)} observation(s) with no ranking found (shown as Not Available, not plotted).")
        st.dataframe(df.drop(columns=["id"]).fillna("Not Available"), width="stretch", hide_index=True)
        with st.expander("Delete an observation"):
            oid = st.number_input("Observation id", int(df["id"].min()), int(df["id"].max()), int(df["id"].max()))
            if st.button("Delete"):
                db.delete_rank_obs(int(oid))
                st.rerun()

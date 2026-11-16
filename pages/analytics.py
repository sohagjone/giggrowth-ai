import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from database import db_manager as db
from modules import state, ui, analytics_engine as AE, report_generator as R

ui.setup("Performance Analytics", "Impressions, clicks, CTR, orders and revenue from **your imported Fiverr analytics** (not exposed by the MCP).", "📈")
acct = state.bootstrap()
if acct:
    with st.expander("📥 Import analytics (CSV / Excel)", expanded=db.load_perf().empty):
        st.markdown("Export your gig analytics from Fiverr (Business → Analytics) or use the template. Needs at least **date, impressions, clicks**; "
                    "**gig, orders, revenue** are optional.")
        st.download_button("Download CSV template", AE.template_csv(), "analytics_template.csv", "text/csv")
        up = st.file_uploader("Upload file", type=["csv", "xlsx", "xls"])
        if up is not None:
            if up.size > 10 * 1024 * 1024:
                st.error("File larger than 10 MB.")
            else:
                try:
                    raw = AE.read_upload(up.name, up.getvalue())
                    st.dataframe(raw.head(5), width="stretch", hide_index=True)
                    auto = AE.detect_columns(raw)
                    cols = ["— none —"] + list(raw.columns)
                    m = {}
                    cc = st.columns(6)
                    for col, key in zip(cc, ["date", "gig", "impressions", "clicks", "orders", "revenue"]):
                        sel = col.selectbox(key.title(), cols, index=cols.index(auto[key]) if auto[key] in cols else 0, key="map_" + key)
                        m[key] = None if sel == "— none —" else sel
                    default_gig = st.text_input("Gig name if the file has no gig column", "All gigs")
                    if st.button("Import", type="primary"):
                        df = AE.normalise(raw, m, default_gig)
                        n = db.save_perf(df)
                        st.success(f"Imported {n:,} rows (replaced previous import).")
                        st.rerun()
                except Exception as e:
                    st.error(f"Could not import: {e}")
    perf = state.perf_df()
    if perf is None:
        ui.not_available("Performance data", "Import an analytics file above to see impressions, clicks, CTR, orders and revenue.")
    else:
        gigs = sorted(perf["gig"].unique())
        sel = st.multiselect("Gigs", gigs, default=gigs[:6])
        freq = st.radio("Granularity", ["Daily", "Weekly", "Monthly"], horizontal=True)
        d = perf[perf["gig"].isin(sel)]
        if d.empty:
            st.info("Select at least one gig.")
        else:
            s = AE.summarize(d)
            c = st.columns(6)
            ui.kpi(c[0], "Impressions", ui.fmt_num(s["impressions"]))
            ui.kpi(c[1], "Clicks", ui.fmt_num(s["clicks"]))
            ui.kpi(c[2], "CTR", f"{s['ctr']:.2f}%" if not np.isnan(s["ctr"]) else "Not Available", "Clicks ÷ Impressions × 100")
            ui.kpi(c[3], "Orders", ui.fmt_num(s["orders"]))
            ui.kpi(c[4], "Click→order", f"{s['click_to_order']:.2f}%" if not np.isnan(s["click_to_order"]) else "Not Available", "Orders ÷ Clicks × 100")
            ui.kpi(c[5], "Revenue", f"${s['revenue']:,.0f}" if not np.isnan(s["revenue"]) else "Not Available")
            t = st.columns(3)
            for col, (k, lab) in zip(t, [("impressions", "Impressions"), ("ctr", "CTR"), ("click_to_order", "Conversion")]):
                tr = AE.trend(d, k)
                col.metric(f"{lab} trend (14d vs prior 14d)", tr["direction"], f"{tr['pct']:+.1f}%" if tr["pct"] is not None else None)
            ts = AE.timeseries(d, {"Daily": "D", "Weekly": "W", "Monthly": "M"}[freq])
            for key, title in [("impressions", "Impressions over time"), ("clicks", "Clicks over time"), ("ctr", "CTR % over time"), ("orders", "Orders over time"), ("revenue", "Revenue over time")]:
                if ts[key].notna().any():
                    f = px.line(ts, x="date", y=key, color="gig", markers=freq != "Daily", template="plotly_white", title=title)
                    f.update_layout(height=300, margin=dict(t=40, b=0))
                    st.plotly_chart(f, width="stretch")
                else:
                    st.caption(f"{title}: Not Available (column not in your file).")
            st.subheader("Gig comparison")
            bg = AE.by_gig(d).rename(columns={"ctr": "CTR %", "click_to_order": "Click→order %", "impression_to_order": "Impr→order %", "aov": "Avg order value"})
            st.dataframe(bg, width="stretch", hide_index=True)
            st.subheader("Funnel diagnosis")
            for g_ in sel:
                for dg in AE.diagnose(d[d["gig"] == g_], d):
                    st.markdown(f"**{g_}** — {ui.badge('Verified' if dg['type'] == 'Verified' else 'Info')} {dg['text']}", unsafe_allow_html=True)
            with st.expander("Metric definitions"):
                st.markdown("- **CTR** = Clicks ÷ Impressions × 100\n- **Click→order** = Orders ÷ Clicks × 100 (primary conversion rate)\n- **Impression→order** = Orders ÷ Impressions × 100\n"
                            "- **Average order value** = Revenue ÷ Orders\n- Zero denominators show *Not Available*, never 0. Trends compare the latest 14 days with the 14 before and need ≥ 28 days of data.")
            st.download_button("⬇️ Download gig performance (Excel)", R.performance_xlsx(d), "gig_performance.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if st.button("Delete imported analytics"):
            db.clear_perf()
            st.rerun()

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import db_manager as db
from modules import state, ui, report_generator as R
from modules.seo_engine import score_band, WEIGHTS

ui.setup("Gig SEO Audit", "Evidence-based audit of every published gig. **Internal AI audit score — not an official Fiverr ranking score.**", "🔍")
acct = state.bootstrap()
if acct:
    ui.source_banner(acct)
    au = state.audits(acct)
    t1, t2, t3 = st.tabs(["Portfolio", "Gig detail", "Gig metadata (manual)"])
    with t1:
        rows = [{"Gig": a["slug"], "Score": a["total"], "Band": score_band(a["total"]), "Projected*": a["projected"], "Confidence": f"{a['confidence']:.0%}",
                 "Primary keyword": a["primary_keyword"], "Weakest areas": ", ".join(c.name for c in a["weakest"])} for a in au]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("*Projected assumes fixable recommendations are implemented (75% realisation) — an internal estimate, not a forecast of Fiverr results.")
        st.download_button("⬇️ Download full SEO audit (PDF)", R.audit_pdf(acct, au), "gig_seo_audit.pdf", "application/pdf")
    with t2:
        g = state.pick_gig(acct, "audit_gig")
        a = next(x for x in au if x["slug"] == g["slug"])
        if not a["title_verified"]:
            st.warning(f"Title is **derived from the URL slug** ('{a['title']}'). The MCP doesn't expose the exact live title — enter it in *Gig metadata* for a verified audit.")
        c = st.columns(4)
        ui.kpi(c[0], "Overall (internal)", f"{a['total']}/100", score_band(a["total"]))
        ui.kpi(c[1], "Projected after fixes", f"{a['projected']}/100", "Internal estimate")
        ui.kpi(c[2], "Confidence", f"{a['confidence']:.0%}", "Share of checks verifiable with current data")
        ui.kpi(c[3], "Primary keyword", a["primary_keyword"] or "—")
        cats = a["categories"]
        fig = go.Figure(go.Scatterpolar(r=[c_.score / c_.weight * 100 for c_ in cats] + [cats[0].score / cats[0].weight * 100],
                                        theta=[c_.name for c_ in cats] + [cats[0].name], fill="toself", line_color="#0B6E4F"))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), height=380, margin=dict(t=20, b=20), showlegend=False, template="plotly_white")
        l, r = st.columns([2, 3])
        with l:
            st.plotly_chart(fig, width="stretch")
        with r:
            st.dataframe(pd.DataFrame([{"Category": c_.name, "Score": round(c_.score, 1), "Max": c_.weight, "Verified checks": f"{c_.confidence:.0%}"} for c_ in cats]), width="stretch", hide_index=True)
        icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "unknown": "❔"}
        for c_ in cats:
            with st.expander(f"{c_.name} — {c_.score:.1f}/{c_.weight}"):
                st.dataframe(pd.DataFrame([{"": icon[k.status], "Check": k.name, "Points": f"{k.pts:g}/{k.max:g}" if k.status != "unknown" else "—", "Finding": k.note} for k in c_.checks]), width="stretch", hide_index=True)
        st.subheader("Recommendations")
        st.dataframe(pd.DataFrame([{"Priority": r_["priority"], "Area": r_["area"], "Finding": r_["finding"], "Recommended change": r_["change"], "Expected benefit": r_["benefit"]} for r_ in a["recommendations"]]),
                     width="stretch", hide_index=True)
        st.caption("Priority High/Medium/Low = potential audit-point gain. 'Data' = missing input that completes the audit. Nothing here changes your live gig.")
        with st.expander("Current description (plain text)"):
            st.text(g["description"])
    with t3:
        st.markdown("The MCP does not expose these fields. Enter them from your gig editor to complete the audit (stored locally in SQLite).")
        g = state.pick_gig(acct, "meta_gig")
        m = db.get_meta(g["slug"])
        with st.form("meta_form"):
            title = st.text_input("Exact live title (text after 'I will')", m.get("title") or "", max_chars=120)
            kw = st.text_input("Primary keyword (optional override)", m.get("primary_keyword") or "", max_chars=60)
            tags = st.text_input("Search tags (comma-separated, max 5)", m.get("tags") or "", max_chars=200)
            c1, c2 = st.columns(2)
            cat = c1.text_input("Category", m.get("category") or "", max_chars=80)
            sub = c2.text_input("Subcategory", m.get("subcategory") or "", max_chars=80)
            c3, c4, c5 = st.columns(3)
            faq = c3.number_input("FAQ count", 0, 30, int(m["faq_count"]) if m.get("faq_count") is not None else 0)
            req = c4.number_input("Requirement questions", 0, 30, int(m["requirements_count"]) if m.get("requirements_count") is not None else 0)
            has_meta = st.checkbox("I have entered real FAQ/requirement counts above", value=m.get("faq_count") is not None)
            if st.form_submit_button("Save metadata"):
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]
                if len(tag_list) > 5:
                    st.error("Fiverr allows at most 5 tags.")
                else:
                    db.save_meta(g["slug"], title=title.strip(), primary_keyword=kw.strip(), tags=", ".join(tag_list), category=cat.strip(), subcategory=sub.strip(),
                                 faq_count=int(faq) if has_meta else None, requirements_count=int(req) if has_meta else None, gallery_count=None, has_video=None, notes="")
                    st.success("Saved. Re-open *Gig detail* to see the updated, higher-confidence audit.")

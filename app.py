"""GigGrowth AI – Fiverr SEO & Intelligence. Entry point: `streamlit run app.py`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

st.set_page_config(page_title="GigGrowth AI – Fiverr SEO & Intelligence", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

PAGES = [
    ("pages/dashboard.py", "Dashboard", "📊", True),
    ("pages/account.py", "My Fiverr Account", "👤", False),
    ("pages/gig_audit.py", "Gig SEO Audit", "🔍", False),
    ("pages/keywords.py", "Keyword Research", "🔑", False),
    ("pages/ranking_tracker.py", "Search Position Tracker", "📍", False),
    ("pages/analytics.py", "Performance Analytics", "📈", False),
    ("pages/competitors.py", "Competitor Intelligence", "🏁", False),
    ("pages/title_generator.py", "AI Title Generator", "✍️", False),
    ("pages/description_optimizer.py", "Description Optimizer", "📝", False),
    ("pages/growth_strategy.py", "Growth Strategy", "🚀", False),
    ("pages/health_monitor.py", "Gig Health Monitor", "🩺", False),
    ("pages/ai_consultant.py", "AI Consultant", "🤖", False),
    ("pages/settings.py", "Settings", "⚙️", False),
]
nav = st.navigation([st.Page(p, title=t, icon=i, default=d) for p, t, i, d in PAGES])
with st.sidebar:
    st.markdown("### GigGrowth AI")
    st.caption("Fiverr SEO & Intelligence · read-only")
nav.run()

"""Session bootstrap shared by all pages."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from database import db_manager as db
from modules import analytics_engine as AE
from modules.fiverr_mcp import MCPError, _cfg, load_account
from modules.seo_engine import audit_account


def default_username() -> str:
    u = _cfg("FIVERR_USERNAME")
    if u:
        return u
    snaps = sorted((ROOT / "data").glob("snapshot_*.json"))
    return snaps[0].stem.replace("snapshot_", "") if snaps else ""


@st.cache_data(ttl=900, show_spinner="Loading your Fiverr data…")
def _load(username: str, prefer_live: bool) -> dict:
    return load_account(username, prefer_live)


def bootstrap() -> dict | None:
    """Ensure session defaults exist and the account is loaded. Returns the account (or None with an error shown)."""
    ss = st.session_state
    ss.setdefault("username", default_username())
    ss.setdefault("prefer_live", True)
    ss.setdefault("competitors", None)
    ss.setdefault("kw_df", None)
    ss.setdefault("chat", [])
    if not ss["username"]:
        st.warning("Set your Fiverr username in Settings.")
        return None
    try:
        acct = _load(ss["username"], ss["prefer_live"])
    except MCPError as e:
        st.error(f"Could not load Fiverr data: {e}")
        return None
    return acct


def refresh() -> None:
    _load.clear()


def audits(account: dict) -> list[dict]:
    return audit_account(account, db.all_meta())


def perf_df():
    df = db.load_perf()
    return df if not df.empty else None


def gig_label(account: dict, slug: str) -> str:
    return slug.replace("-", " ")[:70]


def pick_gig(account: dict, key: str, label: str = "Select a gig"):
    slugs = [g["slug"] for g in account["gigs"]]
    s = st.selectbox(label, slugs, key=key, format_func=lambda x: gig_label(account, x))
    return next(g for g in account["gigs"] if g["slug"] == s)

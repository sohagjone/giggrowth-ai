"""Shared styling and small UI helpers."""
from __future__ import annotations

import streamlit as st

CSS = """
<style>
.block-container {padding-top: 1.6rem; max-width: 1250px;}
h1 {letter-spacing:-0.5px;}
[data-testid="stMetric"] {background: transparent;}
.gg-badge {display:inline-block;padding:2px 10px;border-radius:999px;font-size:0.75rem;font-weight:600;margin-right:6px;}
.gg-live {background:#DDF4E7;color:#0B6E4F;} .gg-snap {background:#FFF1D6;color:#8A5A00;}
.gg-ver {background:#DDF4E7;color:#0B6E4F;} .gg-est {background:#FFF1D6;color:#8A5A00;} .gg-hyp {background:#E8E6FA;color:#4B3FA0;}
.gg-miss {background:#FDE4E4;color:#A12727;}
.gg-sub {color:#6b7280;margin-top:-0.6rem;margin-bottom:1rem;}
</style>
"""
EVID_CLASS = {"Verified": "gg-ver", "Estimate": "gg-est", "Hypothesis": "gg-hyp", "Data limit": "gg-miss", "Info": "gg-ver"}


def setup(title: str, subtitle: str = "", icon: str = "") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(f"{icon} {title}".strip())
    if subtitle:
        st.markdown(f"<div class='gg-sub'>{subtitle}</div>", unsafe_allow_html=True)


def source_banner(account: dict) -> None:
    if account["source"] == "live":
        st.markdown(f"<span class='gg-badge gg-live'>LIVE · Fiverr MCP</span> fetched {account['fetched_at'][:16].replace('T', ' ')} UTC", unsafe_allow_html=True)
    else:
        st.markdown(f"<span class='gg-badge gg-snap'>OFFLINE SNAPSHOT</span> real Fiverr MCP data captured {account['fetched_at'][:10]} — live connection unavailable.", unsafe_allow_html=True)
        for w in account.get("warnings", []):
            with st.expander("Why the live connection failed"):
                st.caption(w)


def badge(kind: str, text: str | None = None) -> str:
    return f"<span class='gg-badge {EVID_CLASS.get(kind, 'gg-est')}'>{text or kind}</span>"


def kpi(col, label: str, value, help: str | None = None, delta=None) -> None:
    with col:
        with st.container(border=True):
            st.metric(label, value, delta=delta, help=help)


def not_available(what: str, how: str) -> None:
    st.info(f"**{what}: Not Available.** {how}")


def fmt_num(x, nd: int = 0) -> str:
    try:
        import math
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "Not Available"
        return f"{x:,.{nd}f}"
    except Exception:
        return str(x)

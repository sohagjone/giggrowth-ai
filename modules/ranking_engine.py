"""Search position tracker (Module 5).

There is NO verified source for Fiverr search position: Fiverr search is personalised, rate-limited and bot-protected,
and this app does not scrape it or bypass CAPTCHA/authentication. Positions are therefore MANUAL observations that
you record after searching in your own browser. A manual observation is not an official Fiverr ranking metric.
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote_plus

import pandas as pd

from modules.text_utils import slug_from_url


def search_url(keyword: str, category: str = "") -> str:
    return f"https://www.fiverr.com/search/gigs?query={quote_plus(keyword)}"


def validate(keyword: str, gig: str, position: int | None, page: int | None) -> list[str]:
    errs = []
    if not (keyword or "").strip():
        errs.append("Keyword is required.")
    if not slug_from_url(gig or ""):
        errs.append("Gig URL or slug is required.")
    if position is not None and not (1 <= int(position) <= 1000):
        errs.append("Position must be between 1 and 1000 (leave blank if the gig was not found).")
    if page is not None and not (1 <= int(page) <= 100):
        errs.append("Search page must be between 1 and 100.")
    return errs


def make_row(gig: str, keyword: str, position: int | None, page: int | None, category: str, location: str, context: str,
             competitors_ahead: str, when: datetime | None = None) -> dict:
    return {"observed_at": (when or datetime.now()).strftime("%Y-%m-%d %H:%M"), "gig_slug": slug_from_url(gig), "keyword": keyword.strip().lower(),
            "position": int(position) if position else None, "search_page": int(page) if page else None, "category": category.strip(),
            "location": location.strip(), "context": context.strip(), "competitors_ahead": competitors_ahead.strip()}


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    for (slug, kw), g in df.sort_values("observed_at").groupby(["gig_slug", "keyword"]):
        last, prev = g.iloc[-1], (g.iloc[-2] if len(g) > 1 else None)
        lp = last["position"]
        if pd.isna(lp):
            status = "No observed ranking"
        elif prev is None:
            status = "First observation"
        elif pd.isna(prev["position"]):
            status = "Newly observed"
        else:
            d = int(prev["position"] - lp)
            status = "Improved" if d > 0 else ("Declined" if d < 0 else "Unchanged")
        rows.append({"Gig": slug, "Keyword": kw, "Latest position": "Not Available" if pd.isna(lp) else int(lp),
                     "Previous": "—" if prev is None or pd.isna(prev["position"]) else int(prev["position"]), "Status": status,
                     "Observations": len(g), "Last observed": last["observed_at"]})
    return pd.DataFrame(rows)

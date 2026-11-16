"""Performance analytics (Module 6). Works on data imported from Fiverr's analytics export (CSV/Excel).

Metric definitions (documented in the UI):
  CTR                      = Clicks / Impressions × 100
  Click→Order conversion   = Orders / Clicks × 100          (primary conversion metric)
  Impression→Order rate    = Orders / Impressions × 100
  Average order value      = Revenue / Orders
Zero denominators return NaN, never 0 — so missing data is never shown as a real zero.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

SYNONYMS = {
    "date": ["date", "day", "period", "week", "month", "time"],
    "gig": ["gig", "gig title", "gig name", "gig_title", "gig id", "service", "title"],
    "impressions": ["impressions", "impression", "views", "gig impressions"],
    "clicks": ["clicks", "click", "gig clicks"],
    "orders": ["orders", "order", "orders count", "completed orders"],
    "revenue": ["revenue", "earnings", "sales", "amount", "income", "gmv"],
}
REQUIRED = ["date", "impressions", "clicks"]


def template_csv() -> str:
    return ("date,gig,impressions,clicks,orders,revenue\n"
            "2026-10-01,Example gig A (replace with your gig),420,12,1,25\n"
            "2026-10-02,Example gig A (replace with your gig),388,9,0,0\n")


def read_upload(name: str, data: bytes) -> pd.DataFrame:
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data))
    return pd.read_csv(io.BytesIO(data))


def detect_columns(df: pd.DataFrame) -> dict[str, str | None]:
    cols = {c: str(c).strip().lower() for c in df.columns}
    mapping: dict[str, str | None] = {}
    for key, syns in SYNONYMS.items():
        hit = next((c for c, l in cols.items() if l in syns), None) or next((c for c, l in cols.items() if any(s in l for s in syns)), None)
        mapping[key] = hit
    return mapping


def normalise(df: pd.DataFrame, mapping: dict[str, str | None], default_gig: str = "All gigs") -> pd.DataFrame:
    missing = [k for k in REQUIRED if not mapping.get(k)]
    if missing:
        raise ValueError(f"Missing required column mapping: {', '.join(missing)}")
    out = pd.DataFrame({"date": pd.to_datetime(df[mapping["date"]], errors="coerce")})
    out["gig"] = df[mapping["gig"]].astype(str) if mapping.get("gig") else default_gig
    for k in ["impressions", "clicks", "orders", "revenue"]:
        out[k] = pd.to_numeric(df[mapping[k]], errors="coerce") if mapping.get(k) else np.nan
    out = out.dropna(subset=["date"])
    for k in ["impressions", "clicks"]:
        out[k] = out[k].fillna(0)
    return out.reset_index(drop=True)


def _div(a, b):
    return np.where(b > 0, a / np.where(b > 0, b, 1), np.nan)


def add_rates(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["ctr"] = _div(d["clicks"], d["impressions"]) * 100
    d["click_to_order"] = _div(d["orders"], d["clicks"]) * 100
    d["impression_to_order"] = _div(d["orders"], d["impressions"]) * 100
    d["aov"] = _div(d["revenue"], d["orders"])
    return d


def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    imp, clk = df["impressions"].sum(), df["clicks"].sum()
    ords = df["orders"].sum() if df["orders"].notna().any() else np.nan
    rev = df["revenue"].sum() if df["revenue"].notna().any() else np.nan
    return {
        "impressions": imp, "clicks": clk, "orders": ords, "revenue": rev,
        "ctr": clk / imp * 100 if imp else np.nan,
        "click_to_order": ords / clk * 100 if clk and not np.isnan(ords) else np.nan,
        "impression_to_order": ords / imp * 100 if imp and not np.isnan(ords) else np.nan,
        "aov": rev / ords if ords and not np.isnan(rev) else np.nan,
        "start": df["date"].min(), "end": df["date"].max(), "days": df["date"].nunique(),
    }


def by_gig(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("gig", as_index=False).agg(impressions=("impressions", "sum"), clicks=("clicks", "sum"),
                                              orders=("orders", lambda s: s.sum(min_count=1)), revenue=("revenue", lambda s: s.sum(min_count=1)))
    return add_rates(g).sort_values("impressions", ascending=False)


def timeseries(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    rule = {"D": "D", "W": "W", "M": "MS"}[freq]
    g = df.set_index("date").groupby("gig").resample(rule).agg({"impressions": "sum", "clicks": "sum",
                                                                  "orders": lambda s: s.sum(min_count=1), "revenue": lambda s: s.sum(min_count=1)}).reset_index()
    return add_rates(g)


def trend(df: pd.DataFrame, metric: str, window_days: int = 14) -> dict:
    """Compare the most recent window with the window before it. Returns direction + % change, or 'Insufficient data'."""
    if df.empty:
        return {"direction": "Insufficient data", "pct": None}
    end = df["date"].max()
    cur = df[df["date"] > end - pd.Timedelta(days=window_days)]
    prev = df[(df["date"] <= end - pd.Timedelta(days=window_days)) & (df["date"] > end - pd.Timedelta(days=2 * window_days))]
    if cur.empty or prev.empty or (end - df["date"].min()).days < 2 * window_days - 1:
        return {"direction": "Insufficient data", "pct": None}

    def val(x):
        s = summarize(x)
        return s.get(metric)
    a, b = val(cur), val(prev)
    if a is None or b is None or np.isnan(a) or np.isnan(b) or b == 0:
        return {"direction": "Insufficient data", "pct": None}
    pct = (a - b) / b * 100
    return {"direction": "Up" if pct > 5 else ("Down" if pct < -5 else "Flat"), "pct": pct, "current": a, "previous": b, "window_days": window_days}


def diagnose(df: pd.DataFrame, portfolio: pd.DataFrame | None = None) -> list[dict]:
    """Rule-based reading of one gig's funnel. Comparisons are RELATIVE (to the gig's own history or your other gigs)."""
    s = summarize(df)
    out = []
    if not s:
        return out
    ti = trend(df, "impressions")
    if ti["direction"] == "Down":
        out.append({"type": "Verified", "text": f"Impressions are down {abs(ti['pct']):.0f}% vs the previous {ti['window_days']} days. Causes are not visible in the data — check recent edits, seasonality, order cancellations and competitor changes."})
    if s["impressions"] >= 300 and s["clicks"] == 0:
        out.append({"type": "Verified", "text": "Impressions but zero clicks: the title/thumbnail is not earning attention. Test a new thumbnail and a clearer, benefit-led title."})
    elif portfolio is not None and len(portfolio) > 1 and not np.isnan(s["ctr"]):
        avg = portfolio["clicks"].sum() / max(1, portfolio["impressions"].sum()) * 100
        if s["ctr"] < avg * 0.7:
            out.append({"type": "Verified", "text": f"CTR {s['ctr']:.2f}% is well below your portfolio average ({avg:.2f}%). Thumbnail/title are the first things to test."})
    if s["clicks"] >= 30 and (not np.isnan(s["orders"])) and s["orders"] == 0:
        out.append({"type": "Verified", "text": f"{s['clicks']:.0f} clicks and no orders: the page is not converting. Review package clarity, price vs competitors, FAQs and reviews relevant to this service."})
    if not out:
        out.append({"type": "Info", "text": "No clear funnel problem is detectable from this data alone."})
    return out

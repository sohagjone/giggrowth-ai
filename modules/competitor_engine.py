"""Competitor intelligence (Module 7) — public marketplace data only (via Fiverr MCP). Never fabricates competitor data."""
from __future__ import annotations

from collections import Counter
from statistics import median

import pandas as pd

from modules.fiverr_mcp import FiverrMCPClient, MCPError, normalize_gig
from modules.text_utils import content_tokens, title_from_slug

DEFAULT_BRIEFS = [
    "{kw} expert",
    "{kw} developer for small business",
    "custom {kw} setup and integration",
]


def discover(kw: str, briefs: list[str] | None = None, filters: dict | None = None) -> tuple[list[dict], list[str]]:
    """Run several differently-worded searches (find_freelancers returns max 5 sellers per call) and de-duplicate."""
    c = FiverrMCPClient()
    errors, sellers, seen = [], [], set()
    for b in (briefs or [t.format(kw=kw) for t in DEFAULT_BRIEFS]):
        try:
            for s in c.find_sellers(b, filters):
                if s.get("username") and s["username"] not in seen:
                    seen.add(s["username"])
                    sellers.append(s)
        except MCPError as e:
            errors.append(str(e))
            break
    return sellers, errors


def fetch_gigs(usernames: list[str]) -> tuple[dict[str, list[dict]], list[str]]:
    c = FiverrMCPClient()
    out, errors = {}, []
    for u in usernames:
        try:
            out[u] = [normalize_gig(g, u) for g in c.get_gigs(u)]
        except MCPError as e:
            errors.append(f"{u}: {e}")
    return out, errors


def sellers_df(sellers: list[dict]) -> pd.DataFrame:
    rows = []
    for s in sellers:
        rows.append({
            "Seller": s.get("username"), "Name": s.get("displayName"), "Headline": s.get("oneLinerTitle"),
            "Rating": (s.get("rating") or {}).get("score"), "Reviews": s.get("userBuyingReviewsCount"),
            "Completed orders": s.get("completedOrdersCount"), "Response (h)": s.get("responseTimeHours"),
            "Country": s.get("countryName"), "Skills": ", ".join(s.get("skills") or []), "URL": s.get("url"),
        })
    return pd.DataFrame(rows)


def gigs_df(gigs_by_seller: dict[str, list[dict]]) -> pd.DataFrame:
    rows = []
    for u, gs in gigs_by_seller.items():
        for g in gs:
            prices = [p["price"] for p in g["packages"] if p["price"] is not None]
            rows.append({"Seller": u, "Gig (title derived from URL)": g["derived_title"], "Basic $": prices[0] if prices else None,
                         "Top tier $": prices[-1] if prices else None, "Packages": len(prices), "URL": g["url"]})
    return pd.DataFrame(rows)


def my_terms(account: dict) -> set[str]:
    t = account["profile"].get("title", "") + " " + account["profile"].get("description", "") + " " + " ".join(g["derived_title"] + " " + g["description"] for g in account["gigs"])
    return set(content_tokens(t))


def analyse(account: dict, sellers: list[dict], gigs_by_seller: dict[str, list[dict]] | None = None) -> dict:
    """Return evidence-based comparisons. Everything is computed from the loaded public data."""
    n = len(sellers)
    skills = Counter(sk.strip().lower() for s in sellers for sk in (s.get("skills") or []))
    mine = my_terms(account)
    gaps = [(k, v) for k, v in skills.most_common(40) if v >= 2 and not all(t in mine for t in content_tokens(k))]
    head_terms = Counter(t for s in sellers for t in set(content_tokens(s.get("oneLinerTitle") or "")))
    ratings = [(s.get("rating") or {}).get("score") for s in sellers if (s.get("rating") or {}).get("score")]
    reviews = [s.get("userBuyingReviewsCount") or 0 for s in sellers]
    res = {
        "n": n, "top_skills": skills.most_common(12), "skill_gaps": gaps[:10], "headline_terms": head_terms.most_common(10),
        "median_reviews": median(reviews) if reviews else None, "median_rating": median(ratings) if ratings else None,
        "my_reviews": (account["profile"].get("rating") or {}).get("count"), "my_rating": (account["profile"].get("rating") or {}).get("score"),
        "enough": n >= 10,
    }
    if gigs_by_seller:
        basics = [p for gs in gigs_by_seller.values() for g in gs for p in [g["packages"][0]["price"]] if g["packages"] and p]
        res["competitor_basic_prices"] = sorted(basics)
        res["competitor_basic_median"] = median(basics) if basics else None
    return res


def insights(account: dict, a: dict) -> list[dict]:
    """Plain-language findings; each tagged Verified (counted from loaded data) or Hypothesis."""
    out = []
    if not a["n"]:
        return out
    if not a["enough"]:
        out.append({"type": "Data limit", "text": f"Only {a['n']} competitor sellers loaded; the brief asks for 10+. Run more searches or widen the keyword to reach 10."})
    if a["median_reviews"] is not None and a["my_reviews"]:
        out.append({"type": "Verified", "text": f"Loaded competitors have a median of {a['median_reviews']:.0f} reviews vs your {a['my_reviews']} — but yours are mostly web-development reviews, not automation (see Gig SEO Audit)."})
    for k, v in a["skill_gaps"][:5]:
        out.append({"type": "Verified", "text": f"'{k}' is listed by {v}/{a['n']} loaded competitors and does not appear in your profile or gig copy."})
    if a.get("competitor_basic_median"):
        out.append({"type": "Verified", "text": f"Median entry (Basic) package price among loaded competitor gigs: ${a['competitor_basic_median']:.0f}."})
    out.append({"type": "Hypothesis", "text": "Competitor headlines name a concrete deliverable (e.g., 'Document AI', 'API Integrations'). A headline naming the specific outcome you sell may lift clicks — test it, don't assume it."})
    return out

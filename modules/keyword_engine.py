"""Keyword research (Module 4).

HONESTY RULES: Fiverr does not publish search volume or competition. Nothing here is a measured volume.
 * Candidates are TEMPLATE-GENERATED phrases built from your service/gig text — labelled as such.
 * 'Competition evidence' is only what we can count: how many loaded competitor profiles use the phrase.
 * 'Opportunity' is a qualitative High/Medium/Low judgement from relevance, specificity, intent and that evidence.
"""
from __future__ import annotations

import re

import pandas as pd

from modules.seo_engine import infer_primary_keyword
from modules.text_utils import content_tokens, slug_from_url, title_from_slug, top_terms

PRESET_SERVICES = ["Market Research", "Competitor Analysis", "Competitive Intelligence", "Market Analysis", "TAM/SAM/SOM Analysis",
                   "Business Research", "Financial Research", "Data Analysis", "n8n Workflow Automation", "PDF Data Extraction",
                   "WordPress Plugin Development", "WooCommerce Store Fix"]

TRANSACTIONAL = {"hire", "expert", "developer", "specialist", "service", "custom", "setup", "set", "fix", "freelancer", "consultant", "professional", "buy", "build", "create"}
INFORMATIONAL = {"how", "what", "tutorial", "guide", "examples", "example", "learn", "template", "free", "tips"}
COMPARE = {"best", "vs", "alternative", "compare", "top", "review"}


def core_phrase_from_input(text: str) -> tuple[str, str]:
    """Accept a service name or a Fiverr gig URL. Returns (core phrase, context text)."""
    text = (text or "").strip()
    if "fiverr.com" in text or ("/" in text and " " not in text):
        slug = slug_from_url(text)
        title = title_from_slug(slug)
        return infer_primary_keyword(title, "") or " ".join(content_tokens(title)[:3]), title
    return text.lower(), text


def _intent(k: str) -> str:
    w = set(content_tokens(k))
    if w & INFORMATIONAL:
        return "Informational"
    if w & COMPARE:
        return "Commercial investigation"
    if w & TRANSACTIONAL:
        return "Transactional"
    return "Navigational / category"


def _relevance(k: str, context: str) -> str:
    kt = set(content_tokens(k))
    ct = set(content_tokens(context))
    if not kt:
        return "Low"
    r = len(kt & ct) / len(kt)
    return "High" if r >= 0.75 else ("Medium" if r >= 0.4 else "Low")


def _competition(k: str, corpus: list[str]) -> tuple[str, float | None]:
    if not corpus:
        return "Not measured (no competitor data loaded)", None
    kt = [t for t in content_tokens(k) if t not in {"for", "with", "using"}]
    n = sum(all(t in c.lower() for t in kt) for c in corpus)
    return f"{n}/{len(corpus)} loaded competitor profiles use all terms", n / len(corpus)


def generate(user_input: str, gig_context: str = "", competitor_corpus: list[str] | None = None, limit: int = 60) -> pd.DataFrame:
    core, ctx = core_phrase_from_input(user_input)
    context = f"{ctx} {gig_context}"
    if not core:
        return pd.DataFrame()
    rows: list[tuple[str, str]] = [(core, "Primary")]
    for m in ["expert", "developer", "specialist", "freelancer", "consultant"]:
        rows.append((f"{core} {m}", "Buyer-intent"))
    rows.append((f"hire {core} expert", "Buyer-intent"))
    for m in ["custom {k}", "professional {k}", "{k} service", "{k} setup", "{k} for hire"]:
        rows.append((m.format(k=core), "Commercial"))
    for aud in ["small business", "ecommerce store", "startups", "agencies", "freelancers"]:
        rows.append((f"{core} for {aud}", "Long-tail"))
    for tool in ["google sheets", "api", "webhook", "excel", "shopify", "wordpress"]:
        if tool not in core:
            rows.append((f"{core} with {tool}", "Long-tail"))
    rows += [(f"fix {core} issues", "Long-tail"), (f"{core} step by step", "Informational"), (f"how to {core}", "Informational")]
    for term, _ in top_terms(context, 10):
        if term not in core and len(term) > 3 and term not in {"will", "services", "service", "work", "including"}:
            rows.append((f"{core} {term}", "Secondary"))
    seen, out = set(), []
    for k, typ in rows:
        k = re.sub(r"\s+", " ", k).strip()
        if k in seen:
            continue
        seen.add(k)
        rel, intent = _relevance(k, context), _intent(k)
        comp_txt, comp_share = _competition(k, competitor_corpus or [])
        pts = {"High": 2, "Medium": 1, "Low": 0}[rel] + (1 if len(k.split()) >= 3 else 0) + (1 if intent == "Transactional" else 0)
        if comp_share is not None:
            pts -= 1 if comp_share >= 0.6 else (0.5 if comp_share >= 0.3 else 0)
        opp = "High" if pts >= 4 else ("Medium" if pts >= 2 else "Low")
        use, place = {
            "Primary": ("Anchor phrase for the whole gig", "Title (first words) + first sentence of description"),
            "Buyer-intent": ("Matches buyers ready to hire", "Description + one search tag"),
            "Commercial": ("Signals a paid service", "Search tags + package names"),
            "Long-tail": ("Narrower, more specific demand", "Search tags (2–3 words) + FAQ answers"),
            "Secondary": ("Supports the primary keyword", "Description body + package text"),
            "Informational": ("Learning intent — weaker for hiring", "FAQ only; avoid in title"),
        }[typ]
        out.append({"Keyword": k, "Type": typ, "Relevance": rel, "Search intent": intent, "Competition evidence": comp_txt,
                    "Opportunity (qualitative)": opp, "Suggested use": use, "Recommended placement": place,
                    "Basis": "Template-generated from your input" + (" + gig text" if gig_context else "")})
    df = pd.DataFrame(out)
    order = {"High": 0, "Medium": 1, "Low": 2}
    df["_o"] = df["Opportunity (qualitative)"].map(order)
    df["_r"] = df["Relevance"].map(order)
    return df.sort_values(["_o", "_r"]).drop(columns=["_o", "_r"]).head(limit).reset_index(drop=True)

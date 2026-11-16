"""Growth strategy (Module 10) and gig health (Module 11).

Every action carries its evidence level:  Verified (found in loaded data) · Estimate (inferred) · Hypothesis (to test).
Nothing here promises rankings, impressions or orders. Priority = impact × evidence ÷ effort.
"""
from __future__ import annotations

import numpy as np

from modules import analytics_engine as AE
from modules.fiverr_mcp import days_since
from modules.seo_engine import portfolio_clusters, score_band

IMPACT = {"High": 3, "Medium": 2, "Low": 1}
EFFORT = {"Low": 1, "Medium": 2, "High": 3}
EVID = {"Verified": 1.0, "Estimate": 0.7, "Hypothesis": 0.4}


def _act(action, why, impact, effort, evidence, area, gig="Portfolio"):
    return {"Action": action, "Why (evidence)": why, "Impact": impact, "Effort": effort, "Evidence": evidence, "Area": area, "Gig": gig,
            "Priority score": round(IMPACT[impact] * EVID[evidence] / EFFORT[effort], 2)}


def typos_in(gig: dict) -> list[tuple[str, str]]:
    import re
    from modules.seo_engine import KNOWN_TYPOS
    txt = (gig["description"] + " " + " ".join(p["title"] + " " + p["description"] for p in gig["packages"])).lower()
    return [(t, fix) for t, fix in KNOWN_TYPOS.items() if re.search(r"\b" + t + r"\b", txt)]


def findings(account: dict, audits: list[dict]) -> list[dict]:
    """Cross-portfolio facts used by the plans, dashboard and consultant. All derived from loaded data."""
    clusters = portfolio_clusters(account)
    n8n = clusters.get("n8n / automation", [])
    total = len(account["gigs"])
    revs = account["reviews"]
    latest = max((r["date"] for r in revs), default="")
    gap = days_since(latest) if latest else None
    low = [r["score"] for r in revs if r["score"] is not None and r["score"] <= 3.7]
    n8n_terms = ["n8n", "automation", "workflow", "google sheets", "invoice", "zapier"]
    n8n_reviews = sum(any(t in r["text"].lower() for t in n8n_terms) for r in revs)
    out = []
    if total and len(n8n) < total:
        out.append({"id": "focus", "type": "Verified", "text": f"Your headline sells n8n automation, but only {len(n8n)} of {total} published gigs are n8n; the rest are web/WordPress/PHP/Photoshop ({', '.join(f'{k}: {len(v)}' for k, v in clusters.items() if k != 'n8n / automation')})."})
    if gap is not None:
        out.append({"id": "recency", "type": "Verified", "text": f"Newest review loaded is {gap} days old ({latest}); {len(revs)} reviews loaded of {account['reviews_summary'].get('count')}."})
    if n8n and n8n_reviews == 0:
        out.append({"id": "n8n_proof", "type": "Verified", "text": f"None of the {len(revs)} loaded reviews mention n8n, automation or workflows — your automation gigs have no visible buyer proof."})
    if low:
        ones = [r for r in revs if r["score"] is not None and r["score"] <= 1.5]
        extra = f", including {len(ones)} one-star review(s) dated {', '.join(sorted({r['date'][:7] for r in ones}))}" if ones else ""
        out.append({"id": "lowrev", "type": "Verified", "text": f"{len(low)} of the {len(revs)} loaded reviews scored 3.7 or lower{extra}. Read them: repeated themes (delays, scope, communication) are fixable with process changes. Seller rating is {account['profile']['rating']['score']}."})
    for a in audits:
        if any("external URLs" in k.note for c in a["categories"] for k in c.checks):
            out.append({"id": "urls:" + a["slug"], "type": "Verified", "text": f"`{a['slug']}` lists external client URLs in the description (may breach Fiverr content rules — verify)."})
        g = next(x for x in account["gigs"] if x["slug"] == a["slug"])
        found = typos_in(g)
        if found:
            out.append({"id": "typo:" + a["slug"], "type": "Verified", "text": f"`{a['slug']}` contains typos in public copy: " + ", ".join(f"'{t}' → '{fix}'" for t, fix in found) + "."})
    prices = [p["price"] for g in account["gigs"] for p in g["packages"][:1] if p["price"]]
    if prices:
        out.append({"id": "prices", "type": "Verified", "text": f"Entry-package prices across your gigs range ${min(prices):.0f}–${max(prices):.0f}."})
    return out


def build_plans(account: dict, audits: list[dict], perf: "object | None" = None, comp: dict | None = None) -> dict[int, list[dict]]:
    F = {f["id"]: f for f in findings(account, audits)}
    clusters = portfolio_clusters(account)
    n8n = clusters.get("n8n / automation", [])
    ranked = sorted(audits, key=lambda a: a["total"])
    P: dict[int, list[dict]] = {7: [], 30: [], 60: [], 90: []}
    # --- 7 days
    for k, f in F.items():
        if k.startswith("urls:"):
            P[7].append(_act("Remove external URLs from the description and replace with a short, general proof statement", f["text"], "Medium", "Low", "Verified", "Trust / compliance", k.split(":", 1)[1]))
        if k.startswith("typo:"):
            P[7].append(_act("Fix typos in package names and description", f["text"], "Medium", "Low", "Verified", "Conversion", k.split(":", 1)[1]))
    P[7].append(_act("Enter exact title, category, subcategory, 5 tags, FAQ count in Gig SEO Audit > Gig metadata", "The MCP does not expose these; the audit is only partly verified until you add them.", "Medium", "Low", "Verified", "Data"))
    if perf is None:
        P[7].append(_act("Export Fiverr analytics (impressions, clicks, orders) and import them", "No performance data loaded, so CTR/conversion problems cannot be located.", "High", "Low", "Verified", "Data"))
    if "recency" in F:
        P[7].append(_act("Message recent happy buyers and ask for a review; add a review request to your delivery message template", F["recency"]["text"], "High", "Low", "Verified", "Trust"))
    w = [a for a in ranked if a["slug"] not in n8n][:1] or ranked[:1]
    if w:
        top = [r for r in w[0]["recommendations"] if r["priority"] in ("High", "Medium")][:1]
        if top:
            P[7].append(_act(top[0]["change"], f"Lowest-scoring gig ({w[0]['total']}/100): {top[0]['finding']}", "Medium", "Low", "Verified", top[0]["area"], w[0]["slug"]))
    # --- 30 days
    if "focus" in F:
        P[30].append(_act("Decide your primary niche (e.g., n8n + WordPress/WooCommerce automation) and align headline, gig order and thumbnails with it", F["focus"]["text"], "High", "Medium", "Verified", "Positioning"))
    for a in [x for x in audits if x["slug"] in n8n]:
        P[30].append(_act("Add 3+ FAQs, a clear 'what's not included' section and a before/after example or short demo video", f"{a['slug']}: FAQs/requirements are not verifiable from the MCP; buyers of technical services convert on clarity.", "Medium", "Medium", "Estimate", "Conversion", a["slug"]))
    if "n8n_proof" in F:
        P[30].append(_act("Offer a small fixed-price pilot to a few past clients (they already trust you) to earn the first reviews for your automation gigs", F["n8n_proof"]["text"], "High", "Medium", "Estimate", "Trust"))
    for a in ranked[:2]:
        P[30].append(_act("Rewrite the opening around the buyer's problem; remove generic phrases ('look no further', 'top-notch')", f"Intent score {next(c.score for c in a['categories'] if c.name.startswith('Buyer')):.1f}/10.", "Medium", "Low", "Verified", "Click & conversion", a["slug"]))
    if comp and comp.get("skill_gaps"):
        P[30].append(_act("Add the most common competitor skills you genuinely offer to profile and gig copy: " + ", ".join(k for k, _ in comp["skill_gaps"][:4]), f"Listed by multiple of the {comp['n']} loaded competitors but absent from your copy.", "Medium", "Low", "Visibility", "n8n gigs"))
    # --- 60 days
    P[60].append(_act("Run one controlled test at a time: new thumbnail on your highest-impression gig, measure CTR for 14 days, then test the title", "CTR improvements need a before/after comparison; you can't attribute changes if several things change together.", "High", "Medium", "Hypothesis", "Click growth"))
    if n8n and clusters.get("WordPress / WooCommerce"):
      P[60].append(_act("Create 1–2 niche n8n gigs from validated keywords (e.g., WooCommerce order → Google Sheets/CRM automation)", "You already sell WooCommerce/WordPress services and n8n workflows; the overlap is a narrower niche with fewer direct competitors (hypothesis — verify counts with Competitor Intelligence).", "High", "High", "Hypothesis", "Business growth"))
    P[60].append(_act("Restructure packages as a ladder: audit/setup (Basic) → build (Standard) → build + 30-day support/monitoring (Premium)", "A support-inclusive premium tier raises order value and creates repeat work.", "Medium", "Medium", "Hypothesis", "Pricing"))
    P[60].append(_act("Pause or archive the lowest-fit gigs if they don't earn orders after the analytics import shows their numbers", "Low-fit gigs dilute the profile's message.", "Medium", "Low", "Hypothesis", "Positioning"))
    # --- 90 days
    P[90].append(_act("Productise: 3 named automation packages with fixed scope, plus an optional monthly maintenance retainer", "Repeat-client revenue is more predictable than one-off orders.", "High", "High", "Hypothesis", "Business growth"))
    P[90].append(_act("Collect 3 short case studies (problem → workflow → hours saved, with client permission) for gig galleries and descriptions", "Proof specific to automation is currently missing from reviews.", "High", "Medium", "Estimate", "Trust"))
    P[90].append(_act("Re-run this audit, re-import analytics and compare CTR / conversion before vs after each change", "Closes the loop: keep what moved the metrics, drop what didn't.", "Medium", "Low", "Verified", "Measurement"))
    for k in P:
        P[k].sort(key=lambda r: -r["Priority score"])
    return P


def health(audit: dict, account: dict, perf_gig=None, comp: dict | None = None, gig: dict | None = None) -> dict:
    comps, miss = [], []
    comps.append(("SEO score (internal)", audit["total"], 30, f"Internal audit score {audit['total']}/100 (confidence {audit['confidence']:.0%})."))
    rating = account["profile"]["rating"]["score"]
    latest = max((r["date"] for r in account["reviews"]), default="")
    gap = days_since(latest) if latest else None
    fb = 100 if rating >= 4.8 else 75 if rating >= 4.5 else 55 if rating >= 4.3 else 35
    if gap is not None and gap > 365:
        fb -= 20
    comps.append(("Customer feedback", max(fb, 0), 20, f"Seller rating {rating}/5; newest review {gap} days ago (profile-level, not gig-level)."))
    for key, label in [("impressions", "Impressions trend"), ("ctr", "CTR trend"), ("click_to_order", "Conversion trend")]:
        if perf_gig is None or perf_gig.empty:
            miss.append(label + " — import analytics")
            continue
        t = AE.trend(perf_gig, key)
        if t["direction"] == "Insufficient data":
            miss.append(label + " — need ≥28 days of data")
        else:
            comps.append((label, {"Up": 85, "Flat": 60, "Down": 30}[t["direction"]], 15, f"{t['direction']} ({t['pct']:+.0f}% vs previous {t['window_days']} days)."))
    bp = gig["packages"][0]["price"] if gig and gig.get("packages") else None
    if comp and comp.get("competitor_basic_median") and bp:
        r = bp / comp["competitor_basic_median"]
        comps.append(("Competitive positioning", 70 if 0.75 <= r <= 1.25 else 50, 5, f"Basic price is {r:.1f}× the competitor median."))
    else:
        miss.append("Competitive positioning — load competitors with gig prices")
    w = sum(c[2] for c in comps)
    score = sum(c[1] * c[2] for c in comps) / w if w else 0
    band = score_band(score)
    known = sum(c[2] for c in comps) / (30 + 20 + 15 * 3 + 5)
    return {"status": band, "score": round(score, 1), "components": comps, "missing": miss, "data_coverage": round(known, 2)}

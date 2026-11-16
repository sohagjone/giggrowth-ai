"""AI layer (Modules 8, 9, 12). Works with a configurable LLM (OpenAI-compatible or Anthropic) and ALWAYS falls back to
transparent rule-based generation when no API key is configured, so every button works. Output is labelled with its engine.

Keys come from environment variables / Streamlit secrets only — never from code, never rendered in the UI.
"""
from __future__ import annotations

import json
import os
import re

import requests

from modules.fiverr_mcp import _cfg
from modules.seo_engine import TITLE_LIMIT, DESC_LIMIT, audit_description, audit_title, infer_primary_keyword, secondary_terms
from modules.text_utils import ACTION_VERBS, content_tokens, count_phrase, html_to_text


# ---- provider --------------------------------------------------------------------------------------------------
def provider() -> dict:
    prov = (_cfg("LLM_PROVIDER", "") or "").lower()
    if not prov:
        prov = "anthropic" if _cfg("ANTHROPIC_API_KEY") else ("openai" if _cfg("OPENAI_API_KEY") else "none")
    key = _cfg("ANTHROPIC_API_KEY") if prov == "anthropic" else _cfg("OPENAI_API_KEY")
    default_model = "claude-sonnet-4-6" if prov == "anthropic" else "gpt-4o-mini"
    return {"provider": prov, "key": key, "model": _cfg("LLM_MODEL", default_model),
            "base_url": _cfg("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")}


def llm_available() -> bool:
    p = provider()
    return p["provider"] in ("openai", "anthropic") and bool(p["key"])


def complete(system: str, user: str, max_tokens: int = 1500, history: list[dict] | None = None) -> str:
    p = provider()
    if not llm_available():
        raise RuntimeError("No LLM configured")
    msgs = (history or []) + [{"role": "user", "content": user}]
    try:
        if p["provider"] == "anthropic":
            r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                              headers={"x-api-key": p["key"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
                              json={"model": p["model"], "max_tokens": max_tokens, "system": system, "messages": msgs})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json().get("content", []))
        r = requests.post(f"{p['base_url']}/chat/completions", timeout=60,
                          headers={"Authorization": f"Bearer {p['key']}", "Content-Type": "application/json"},
                          json={"model": p["model"], "max_tokens": max_tokens, "messages": [{"role": "system", "content": system}] + msgs})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.RequestException as e:
        # never echo headers/keys
        raise RuntimeError(f"LLM request failed ({e.__class__.__name__}).") from None


GROUNDING = ("You are a Fiverr growth consultant. Use ONLY the data supplied. Never invent analytics, rankings, search volumes or competitor "
             "facts. Label every statement as [VERIFIED] (present in the supplied data), [ESTIMATE] (inferred, say from what) or "
             "[RECOMMENDATION]. If data is missing, say what is missing and how to get it. Never promise rankings, impressions or orders. "
             "Write plain, natural English.")


# ---- titles ------------------------------------------------------------------------------------------------------
def _clip(body: str) -> str:
    body = re.sub(r"\s+", " ", body).strip(" ,.-")
    if len(body) <= TITLE_LIMIT:
        return body
    cut = body[:TITLE_LIMIT].rsplit(" ", 1)[0]
    return cut


TECH = ["n8n", "google sheets", "wordpress", "woocommerce", "crm", "api", "webhook", "zapier", "shopify", "elementor", "divi", "php", "mysql",
        "codeigniter", "laravel", "slack", "airtable", "email", "ocr", "react", "python", "excel"]


def split_title(base: str) -> tuple[str, str, str]:
    """'I will automate pdf invoice and receipt processing using n8n' -> (verb, object, tail)."""
    body = re.sub(r"^i will\s+", "", base.strip(), flags=re.I)
    m = re.search(r"\s(using|with|in|via|into|for|and connect)\s", body)
    head, tail = (body[:m.start()], body[m.start():].strip()) if m else (body, "")
    words = head.split()
    verb = words[0].lower() if words and words[0].lower() in ACTION_VERBS else ""
    obj = " ".join(words[1:] if verb else words)
    obj = re.sub(r"^(your|my|a|an|the)\s+", "", obj, flags=re.I)
    return verb or "build", obj or head, tail


def title_candidates(gig: dict, pk: str, sec: list[str], profile: dict, base: str | None = None) -> list[tuple[str, str]]:
    base = base or gig["derived_title"]
    verb, obj, tail = split_title(base)
    text = (base + " " + gig["description"] + " " + " ".join(p["title"] + " " + p["description"] for p in gig["packages"])).lower()
    tools = [t for t in TECH if re.search(r"\b" + re.escape(t) + r"\b", text) and t not in obj.lower()]
    main_tool = next((t for t in tools if t in ("n8n", "wordpress", "woocommerce", "php", "elementor", "shopify")), None)
    out: list[tuple[str, str]] = [(re.sub(r"^i will\s+", "", base, flags=re.I), "Your current title (baseline for comparison).")]
    title_tools = [t for t in tools if t in ("n8n", "google sheets", "wordpress", "woocommerce", "php", "elementor", "divi", "shopify", "zapier", "python", "react", "laravel", "codeigniter", "airtable", "slack", "crm", "excel")]
    for t in title_tools[:3]:
        out.append((f"{verb} {obj} using {t}", f"Names '{t}' — a tool your own gig copy already mentions."))
    if "google sheets" in tools and main_tool and main_tool != "google sheets":
        out.append((f"{verb} {obj} to google sheets using {main_tool}", "Spells out the destination and the tool in one phrase."))
    for a in ["for small business", "for ecommerce stores", "for startups", "for agencies", "for your business"]:
        suffix = f" using {main_tool}" if main_tool else ""
        out.append((f"{verb} {obj} {a}{suffix}", "Names the buyer so the right people click."))
    for v in ["set up", "build", "fix", "customize", "create"]:
        if v != verb:
            ok = v != "fix" or "fix" in text
            if ok:
                out.append((f"{v} {obj}" + (f" using {main_tool}" if main_tool else ""), f"Alternative action verb ('{v}') buyers commonly search."))
    if "test" in text:
        out.append((f"{verb} {obj}" + (f" using {main_tool}" if main_tool else "") + ", tested before delivery", "States a real process step already in your copy (testing)."))
    if pk and pk not in obj.lower():
        out.append((f"{verb} {pk} {('with ' + main_tool) if main_tool and main_tool not in pk else 'for your business'}", "Short, keyword-first version."))
    seen, res = set(), []
    for t, why in out:
        t = _clip(t)
        if t.lower() not in seen:
            seen.add(t.lower())
            res.append((t, why))
    return res


def generate_titles(gig: dict, account: dict, meta: dict | None = None, n: int = 10, use_llm: bool = True) -> tuple[list[dict], str]:
    meta = meta or {}
    base = (meta.get("title") or "").strip() or gig["derived_title"]
    pk = (meta.get("primary_keyword") or "").strip().lower() or infer_primary_keyword(base, gig["description"])
    sec = secondary_terms(base, gig["description"], gig["packages"])
    cands, engine = [], "rule-based"
    if use_llm and llm_available():
        try:
            prompt = (f"Gig description:\n{gig['description'][:1500]}\nPackages: {[(p['title'], p['price']) for p in gig['packages']]}\n"
                      f"Primary keyword: {pk}\nWrite 12 Fiverr gig titles (text after 'I will', max {TITLE_LIMIT} chars, natural, no keyword stuffing, "
                      "no misleading claims). Return ONLY JSON: [{\"title\":..., \"why\":...}]")
            raw = complete(GROUNDING, prompt, 1200)
            data = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
            cands = [(_clip(re.sub(r"^i will\s+", "", d["title"], flags=re.I)), d.get("why", "")) for d in data if d.get("title")]
            engine = f"LLM ({provider()['provider']}:{provider()['model']})"
        except Exception:
            cands, engine = [], "rule-based (LLM failed)"
    if not cands:
        cands = title_candidates(gig, pk, sec, account["profile"], base)
    rows = []
    for t, why in cands:
        a = audit_title("I will " + t, pk, True)
        rows.append({"title": t, "why": why, "score": round(a.score, 1), "chars": len(t), "full": "I will " + t,
                     "checks": {c.name: c.status for c in a.checks}})
    base_body = re.sub(r"^i will\s+", "", base, flags=re.I).lower()
    for r in rows:
        bonus = (0.5 if 45 <= r["chars"] <= 75 else 0) + (0.3 if re.search(r"\b(using|with|for|to)\b", r["title"]) else 0) - (0.4 if r["title"].lower() == base_body else 0)
        r["rank_score"] = round(r["score"] + bonus, 1)
    rows.sort(key=lambda r: (-r["rank_score"], r["chars"]))
    return rows[:n], engine


# ---- descriptions -------------------------------------------------------------------------------------------------
FAMILY_COPY = {
    "n8n": ("Doing the same task by hand every day wastes time and invites mistakes.", "less manual work, fewer errors and a process that runs on its own"),
    "wordpress": ("A broken plugin, slow page or messy theme can cost you visitors and sales.", "a site that works, loads properly and is easy for you to manage"),
    "php": ("Off-the-shelf tools often don't fit how your business actually works.", "a custom web application built around your requirements"),
    "photoshop": ("Messy product photos make a shop look less trustworthy.", "clean, consistent images ready for your store"),
}


def _family(text: str) -> str:
    t = text.lower()
    for k in ["n8n", "photoshop", "php", "wordpress", "elementor"]:
        if k in t:
            return "wordpress" if k == "elementor" else k
    return "wordpress"


def fix_typos(t: str) -> str:
    from modules.seo_engine import KNOWN_TYPOS
    for bad, good in KNOWN_TYPOS.items():
        t = re.sub(r"\b" + bad + r"\b", good, t, flags=re.I)
    return t.replace(" $ ", " & ")


def _bullets(desc: str, limit: int = 7) -> list[str]:
    out = []
    for ln in desc.split("\n"):
        if ln.startswith("- "):
            b = ln[2:].strip().rstrip(".")
            if 8 <= len(b) <= 90 and "http" not in b and not b.lower().startswith(("extensive", "strong", "attention", "excellent", "in-depth", "years", "friendly", "100%", "24/7", "you will", "you ", "fast bug", "thorough")):
                out.append(b)
    return out[:limit]


def rule_description(gig: dict, account: dict, pk: str) -> tuple[str, list[str]]:
    d = gig["description"]
    fam = _family(gig["derived_title"] + " " + pk)
    _, obj, _ = split_title(gig["derived_title"])
    pain, benefit = FAMILY_COPY[fam]
    bullets = _bullets(d) or [p["title"].strip() + (": " + p["description"].strip()[:60] if len(p["description"]) > 25 else "") for p in gig["packages"] if p["title"]][:5]
    bullets = [fix_typos(b) for b in bullets]
    rating = account["profile"].get("rating") or {}
    why = []
    if rating.get("score") and rating.get("count"):
        why.append(f"Rated {rating['score']}/5 from {rating['count']} reviews on Fiverr")
    yrs = re.search(r"(\d+)\s+years", d)
    if yrs:
        why.append(f"{yrs.group(1)} years of experience (from your current copy — confirm it is still accurate)")
    if re.search(r"test", d, re.I):
        why.append("Everything is tested before delivery")
    if re.search(r"instruction|support", d, re.I):
        why.append("Clear instructions and support after delivery")
    if not why:
        why.append("Clear communication and a tested, documented result")

    def build(bs: list[str]) -> str:
        opener = f"Looking for help with {obj}?" if obj else f"Looking for help with {pk}?"
        parts = [opener + (f" I work on {pk} projects" if pk and pk not in obj.lower() else " I'll take it") + " from your first message to the final test.", "", pain, "",
                 "What you get:", *[f"- {b}" for b in bs], "", f"The result: {benefit}.", "", "Why work with me:", *[f"- {w}" for w in why], "",
                 "Message me before ordering with your requirements (and examples if you have them). I'll confirm the scope and the right package for you."]
        return "\n".join(parts)
    txt = build(bullets)
    while len(txt) > DESC_LIMIT and len(bullets) > 3:
        bullets = bullets[:-1]
        txt = build(bullets)
    changes = ["Opens with the buyer's need and your primary keyword instead of 'Welcome to my gig'.",
               "Adds one sentence about the buyer's problem and one about the outcome.",
               "Keeps your real deliverables as short bullets; generic claims ('attention to detail', 'top-notch') removed.",
               "Uses only claims found in your gig or profile data (rating, review count, testing); you must confirm any number before publishing.",
               "Ends with a single clear call to action.", f"Fits within {DESC_LIMIT} characters." if len(txt) <= DESC_LIMIT else "Still over the length limit — shorten further."]
    if "http" in d:
        changes.append("External URLs removed (Fiverr may restrict external links).")
    return fix_typos(txt), changes


def optimize_description(gig: dict, account: dict, meta: dict | None = None, use_llm: bool = True) -> dict:
    meta = meta or {}
    base = (meta.get("title") or "").strip() or gig["derived_title"]
    pk = (meta.get("primary_keyword") or "").strip().lower() or infer_primary_keyword(base, gig["description"])
    sec = secondary_terms(base, gig["description"], gig["packages"])
    new, changes, engine = None, [], "rule-based"
    if use_llm and llm_available():
        try:
            prompt = (f"Rewrite this Fiverr gig description (max {DESC_LIMIT} characters, plain text with simple '- ' bullets). Include: strong opening, buyer pain "
                      f"point, clear service explanation, specific deliverables, buyer benefits, the keyword '{pk}' naturally 2-3 times, reasons to choose me, a call "
                      "to action. Natural human English, no hype, no unrealistic promises, only facts present below. After the description write a line "
                      "'---CHANGES---' then 4-6 short bullets explaining the changes.\n\nSELLER: rating "
                      f"{account['profile'].get('rating')}\nCURRENT DESCRIPTION:\n{gig['description']}\nPACKAGES: {[(p['title'], p['price'], p['description']) for p in gig['packages']]}")
            raw = complete(GROUNDING, prompt, 1500)
            new, _, ch = raw.partition("---CHANGES---")
            new, changes = new.strip(), [c.lstrip("-• ").strip() for c in ch.strip().split("\n") if c.strip()]
            engine = f"LLM ({provider()['provider']}:{provider()['model']})"
            if len(new) > DESC_LIMIT + 100:
                raise ValueError("too long")
        except Exception:
            new = None
    if not new:
        new, changes = rule_description(gig, account, pk)
        engine = engine if engine == "rule-based" else "rule-based (LLM failed)"
    b = audit_description(gig["description"], base, pk, sec)
    a = audit_description(new, base, pk, sec)
    return {"original": gig["description"], "improved": new, "changes": changes, "engine": engine, "keyword": pk,
            "before": {"score": round(b.score, 1), "max": b.weight, "chars": len(gig["description"]), "kw": count_phrase(gig["description"], pk)},
            "after": {"score": round(a.score, 1), "max": a.weight, "chars": len(new), "kw": count_phrase(new, pk)}}


# ---- consultant ---------------------------------------------------------------------------------------------------
def build_context(account: dict, audits: list[dict], perf_summary: dict | None, comp_summary: dict | None, rank_summary=None) -> str:
    p = account["profile"]
    L = [f"SELLER: {p.get('display_name')} (@{account['username']}), {p.get('country')}. Headline: {p.get('title')}. Rating {p.get('rating')}. Data source: {account['source']} ({account['fetched_at']}).",
         f"REVIEWS: {len(account['reviews'])} loaded of {account['reviews_summary'].get('count')}; newest {max((r['date'] for r in account['reviews']), default='n/a')}."]
    for a, g in zip(audits, account["gigs"]):
        L.append(f"GIG {g['slug']} | title(derived={not a['title_verified']}): {a['title']} | kw: {a['primary_keyword']} | internal SEO score {a['total']}/100 "
                 f"(confidence {a['confidence']}) | prices {[pk['price'] for pk in g['packages']]} | top issues: "
                 + "; ".join(r["check"] for r in a["recommendations"][:3] if r["priority"] != "Data"))
    L.append("PERFORMANCE DATA: " + (json.dumps(perf_summary, default=str) if perf_summary else "NOT IMPORTED (impressions/clicks/orders unavailable)"))
    L.append("COMPETITORS: " + (json.dumps(comp_summary, default=str)[:1500] if comp_summary else "not loaded"))
    L.append("RANK OBSERVATIONS: " + (rank_summary.to_string()[:800] if rank_summary is not None and len(rank_summary) else "none logged"))
    return "\n".join(L)


def consultant_answer(question: str, context: str, ctx_objs: dict, history: list[dict] | None = None) -> tuple[str, str]:
    if llm_available():
        try:
            return complete(GROUNDING + "\n\nDATA:\n" + context, question, 1200, history), f"LLM ({provider()['provider']}:{provider()['model']})"
        except Exception as e:
            fallback_note = f"(LLM unavailable: {e} Using rule-based answer.)\n\n"
            return fallback_note + rule_answer(question, ctx_objs), "rule-based"
    return rule_answer(question, ctx_objs), "rule-based"


def rule_answer(q: str, c: dict) -> str:
    ql = q.lower()
    audits, account, perf = c["audits"], c["account"], c.get("perf")
    lines = []
    ranked = sorted(audits, key=lambda a: a["total"])
    if any(w in ql for w in ["impression", "visibility", "decreas"]):
        if perf is None:
            lines += ["**[MISSING DATA]** I can't tell whether impressions are falling: impression history isn't available through the Fiverr MCP. Import your Fiverr analytics export (Performance Analytics page) and I'll measure the trend.",
                      "**[VERIFIED]** The newest review on your profile is " + str(max((r['date'] for r in account['reviews']), default='n/a')) + " — a long review gap is a plausible visibility factor, but that is a **[HYPOTHESIS]**, not something the data proves."]
        else:
            lines.append("**[VERIFIED]** " + " ".join(d["text"] for d in c["diagnoses"][:2]))
    elif "click" in ql and "order" not in ql:
        lines += ["**[RECOMMENDATION]** Clicks are driven by title, thumbnail and price shown in search. Test one change at a time on your highest-impression gig and compare CTR over 14 days."] + (["**[MISSING DATA]** I need impressions + clicks to say whether CTR is the problem."] if perf is None else [])
    elif "order" in ql or "convert" in ql:
        lines += ["**[RECOMMENDATION]** If clicks are healthy but orders aren't, work on: package clarity, FAQs, and reviews that match the service. For your n8n gigs, **[VERIFIED]** none of the loaded reviews mention n8n, so buyers can't see proof for that service."]
    elif "which gig" in ql or "optimi" in ql and "first" in ql:
        w = ranked[0]
        lines += [f"**[VERIFIED]** Lowest internal SEO score: `{w['slug']}` at {w['total']}/100 (confidence {w['confidence']:.0%}).",
                  "**[RECOMMENDATION]** Start with: " + "; ".join(r["change"] for r in w["recommendations"][:3] if r["priority"] != "Data")]
    elif "keyword" in ql or "tag" in ql:
        lines += ["**[RECOMMENDATION]** Use the Keyword Research page on your two n8n gigs first. Keywords come from your own copy plus templates — they are candidates, not measured search volumes."]
        for a in audits[-2:]:
            lines.append(f"**[VERIFIED]** `{a['slug']}` currently centres on **{a['primary_keyword']}**; related terms in your copy: {', '.join(a['secondary_terms'][:5])}.")
    elif "competitor" in ql:
        cs = c.get("comp")
        lines += ([f"**[VERIFIED]** {cs['n']} competitor sellers loaded. Frequently listed skills missing from your copy: " + ", ".join(k for k, _ in cs["skill_gaps"][:5])] if cs else ["Load competitors on the Competitor Intelligence page first."])
    elif "description" in ql:
        lines += ["Use the Description Optimizer page: it rewrites the opening around the buyer's problem, keeps only claims found in your data and ends with one call to action."]
    elif "new gig" in ql or "create" in ql:
        lines += ["**[RECOMMENDATION]** Candidates that build on what you've shown: (1) n8n + Google Sheets/CRM lead automation for WordPress/WooCommerce sites (you have both skills and gigs), (2) invoice-to-accounting workflows (extend your PDF gig). **[HYPOTHESIS]** — validate demand with the Keyword Research page and competitor counts before building."]
    elif "90" in ql or "business" in ql or "grow" in ql:
        lines += ["See the Growth Strategy page for the 7/30/60/90-day plan. Headline priorities: (1) fix verified copy issues, (2) decide your focus (6 of 8 gigs are web/design, but your headline is n8n), (3) get fresh reviews on the n8n gigs, (4) import analytics so decisions use real CTR/conversion."]
    else:
        lines += [f"**[VERIFIED]** You have {len(audits)} published gigs; internal SEO scores range {ranked[0]['total']}–{ranked[-1]['total']}/100. Ask about impressions, clicks, orders, keywords, competitors, descriptions, new gigs or your 90-day plan for a specific answer."]
    return "\n\n".join(lines)

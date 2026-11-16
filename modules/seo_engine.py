"""Internal AI-assisted SEO audit & scoring (Modules 2, 3).

IMPORTANT: scores are an INTERNAL audit heuristic. They are NOT Fiverr's ranking score or any Fiverr-issued metric.
Design rules:
  * Every check is either evidence-based (computed from gig text/packages/reviews) or marked 'unknown' when the input
    (tags, category, FAQs...) is not exposed by the MCP. Unknown checks are excluded from the score and reported
    via a confidence value, so missing data never silently inflates or deflates a score.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from modules.fiverr_mcp import days_since
from modules.text_utils import (ACTION_VERBS, STOPWORDS, content_tokens, count_phrase, ngrams, title_from_slug, tokens)

WEIGHTS = {
    "Title optimization": 20, "Description optimization": 20, "Keyword & tag relevance": 20,
    "Category & metadata relevance": 10, "Buyer intent & positioning": 10, "Packages & pricing clarity": 10,
    "Trust signals & presentation": 10,
}
TITLE_LIMIT = 80          # characters after "I will" (Fiverr title limit at time of writing — verify in the gig editor)
DESC_LIMIT = 1200         # Fiverr description limit at time of writing — verify in the gig editor
KNOWN_TYPOS = {"eliminator": "Elementor", "framwork": "framework", "responseive": "responsive", "alwayys": "always",
               "wordpres": "WordPress", "woocomerce": "WooCommerce", "upto": "up to"}
FILLER = {"will", "gig", "service", "services", "work", "best", "professional", "expert", "quality", "your", "my"}
CTA_WORDS = ["message me", "contact me", "order now", "before ordering", "get started", "let's discuss", "let's talk", "reach out", "send me a message"]
TRUST_WORDS = ["test", "guarantee", "support", "revision", "experience", "years", "satisfaction", "refund", "clear", "instructions", "documentation"]
BENEFIT_WORDS = ["save time", "save", "reduce", "increase", "faster", "efficient", "eliminate", "avoid", "grow", "improve", "automate", "streamline", "boost", "no more", "hours"]
PAIN_OPENERS = ["need", "struggling", "tired of", "are you", "looking for", "want to", "stuck", "frustrat", "want your", "do you"]
AUDIENCE_WORDS = ["business", "store", "startup", "agency", "owner", "ecommerce", "e-commerce", "company", "shop", "freelancer", "team", "website owners"]
COMMERCIAL_WORDS = {"service", "expert", "developer", "freelancer", "custom", "hire", "fix", "setup", "integration", "automation",
                    "development", "design", "conversion", "optimization", "audit", "analysis"}


@dataclass
class Check:
    name: str
    pts: float
    max: float
    status: str                     # pass | warn | fail | unknown
    note: str
    fix: str = ""
    fixable: bool = True


@dataclass
class CategoryResult:
    name: str
    weight: int
    checks: list[Check] = field(default_factory=list)

    @property
    def verified_max(self) -> float:
        return sum(c.max for c in self.checks if c.status != "unknown")

    @property
    def full_max(self) -> float:
        return sum(c.max for c in self.checks)

    @property
    def score(self) -> float:
        vm = self.verified_max
        return 0.0 if vm == 0 else sum(c.pts for c in self.checks if c.status != "unknown") / vm * self.weight

    @property
    def confidence(self) -> float:
        return 0.0 if self.full_max == 0 else self.verified_max / self.full_max


def _status(pts: float, mx: float) -> str:
    r = pts / mx if mx else 0
    return "pass" if r >= 0.8 else ("warn" if r >= 0.4 else "fail")


def _chk(name, pts, mx, note, fix="", fixable=True) -> Check:
    return Check(name, round(pts, 2), mx, _status(pts, mx), note, fix, fixable)


def _unknown(name, mx, note, fix) -> Check:
    return Check(name, 0, mx, "unknown", note, fix)


# ---- keyword inference ------------------------------------------------------------------------------------------
GENERIC_TERMS = {"website", "web", "custom", "issues", "errors", "page", "pages", "any", "work", "complete", "secure", "responsive",
                 "dynamic", "background", "kind", "type", "types", "new", "free", "fast", "full", "simple", "advanced", "basic"}


def infer_primary_keyword(title: str, description: str) -> str:
    """Pick the most 'keyword-like' phrase from the title: chunks split on stop-words/verbs, scored by use in the copy."""
    body = re.sub(r"^i will\s+", "", title.lower())
    chunks, cur = [], []
    for w in tokens(body):
        if w in STOPWORDS or w in ACTION_VERBS or w in FILLER:
            if cur:
                chunks.append(cur)
            cur = []
        else:
            cur.append(w)
    if cur:
        chunks.append(cur)
    cands: list[str] = []
    for ch in chunks:
        ch = [w for w in ch if w not in GENERIC_TERMS]
        if not ch:
            continue
        if len(ch) <= 3:
            cands.append(" ".join(ch))
        cands += ngrams(ch, 2) + [w for w in ch if w not in GENERIC_TERMS]
    cands = [c for c in dict.fromkeys(cands) if c and c not in GENERIC_TERMS]
    if not cands:
        return ""
    desc = description.lower()
    multi_in_copy = [k for k in cands if " " in k and desc.count(k) >= 1]
    cands = [k for k in cands if " " in k or not any(k in m.split() for m in multi_in_copy)] or cands

    def sc(k: str) -> float:
        n = len(k.split())
        c = desc.count(k)
        pen = 2.0 if c == 0 else 0.0
        base = min(c, 4) * 2 if n > 1 else min(c, 2) * 2
        return base - pen + (3.5 if n == 2 else (2.5 if n == 3 else 0)) - (0.3 * max(body.find(k), 0) / 20)
    return max(cands, key=sc)


def secondary_terms(title: str, description: str, packages: list[dict], n: int = 8) -> list[str]:
    text = " ".join([title, description] + [p["title"] + " " + p["description"] for p in packages])
    cnt = Counter(w for w in content_tokens(text) if w not in ACTION_VERBS and w not in FILLER and not w.isdigit()
                  and w not in {"https", "http", "www", "com", "org", "net"})
    return [w for w, _ in cnt.most_common(n)]


# ---- per-category checks ----------------------------------------------------------------------------------------
def audit_title(title: str, pk: str, verified: bool) -> CategoryResult:
    cat = CategoryResult("Title optimization", WEIGHTS["Title optimization"])
    body = re.sub(r"^i will\s+", "", title, flags=re.I).strip()
    L = len(body)
    ws = body.lower().split()
    # length
    if 40 <= L <= TITLE_LIMIT - 5:
        cat.checks.append(_chk("Length", 4, 4, f"{L}/{TITLE_LIMIT} characters — uses the space well."))
    elif L > TITLE_LIMIT:
        cat.checks.append(_chk("Length", 1, 4, f"{L} characters exceeds the {TITLE_LIMIT}-character limit.", "Shorten the title below 80 characters."))
    else:
        cat.checks.append(_chk("Length", 2 if L >= 25 else 1, 4, f"Only {L} characters — room for more searchable detail.", "Add a specific use case or tool after the main keyword."))
    # keyword position
    first5 = " ".join(ws[:6])
    if pk and pk in first5:
        cat.checks.append(_chk("Primary keyword placement", 5, 5, f"'{pk}' appears at the start of the title."))
    elif pk and pk in body.lower():
        cat.checks.append(_chk("Primary keyword placement", 3, 5, f"'{pk}' is in the title but not near the front.", "Move the primary keyword into the first 5–6 words."))
    else:
        cat.checks.append(_chk("Primary keyword placement", 0, 5, "Primary keyword is missing from the title.", "Include the primary keyword in the first words."))
    # clarity
    first = ws[0] if ws else ""
    if first in ACTION_VERBS:
        cat.checks.append(_chk("Service clarity", 3, 3, f"Starts with a clear action verb ('{first}')."))
    else:
        cat.checks.append(_chk("Service clarity", 1, 3, "Title does not open with a clear deliverable verb.", "Start with what the buyer gets: 'build…', 'fix…', 'convert…'."))
    # stuffing
    cnt = Counter(w for w in content_tokens(body))
    dup = [w for w, c in cnt.items() if c > 1]
    cat.checks.append(_chk("No keyword stuffing", 3 if not dup else 1, 3,
                           "No repeated keywords." if not dup else f"Repeated words: {', '.join(dup)}.", "Remove repeated words."))
    # differentiation
    has_spec = bool(re.search(r"\b(using|with|for|in|via)\b", body.lower())) or len(content_tokens(body)) >= 6
    cat.checks.append(_chk("Differentiation / specificity", 3 if has_spec else 1, 3,
                           "Includes a specific tool, audience or use case." if has_spec else "Generic — little to separate it from competing gigs.",
                           "Add a niche qualifier (tool, platform, audience or use case)."))
    # readability
    bad = bool(re.search(r"[A-Z]{4,}", body)) or bool(re.search(r"[^\w\s,&'\-./+()]", body))
    cat.checks.append(_chk("Readability", 0.5 if bad else 2, 2, "Readable, no ALL-CAPS or symbols." if not bad else "Contains ALL-CAPS words or symbols.", "Use plain sentence case."))
    return cat


def audit_description(desc: str, title: str, pk: str, secondary: list[str]) -> CategoryResult:
    cat = CategoryResult("Description optimization", WEIGHTS["Description optimization"])
    low = desc.lower()
    L = len(desc)
    if 500 <= L <= DESC_LIMIT:
        cat.checks.append(_chk("Length", 4, 4, f"{L}/{DESC_LIMIT} characters."))
    elif L > DESC_LIMIT:
        cat.checks.append(_chk("Length", 2, 4, f"{L} characters (text extracted from HTML) is above the {DESC_LIMIT} limit — check the live gig.", "Tighten to the limit; cut generic filler first."))
    else:
        cat.checks.append(_chk("Length", 2 if L >= 250 else 1, 4, f"Only {L} characters.", "Expand with deliverables and buyer benefits."))
    if pk and pk in low[:200]:
        cat.checks.append(_chk("Primary keyword in opening", 3, 3, "Primary keyword appears in the first lines."))
    elif pk and pk in low:
        cat.checks.append(_chk("Primary keyword in opening", 1.5, 3, "Keyword appears, but not in the opening.", "Mention the primary keyword in the first sentence."))
    else:
        cat.checks.append(_chk("Primary keyword in opening", 0, 3, "Primary keyword not found in description.", "Add the primary keyword naturally in the first sentence."))
    cov = [t for t in secondary if t in low]
    cat.checks.append(_chk("Secondary keyword coverage", 3 * (len(cov) / max(1, len(secondary))), 3,
                           f"{len(cov)}/{len(secondary)} related terms covered.", "Cover missing related terms naturally: " + ", ".join(t for t in secondary if t not in low)[:120]))
    bullets = desc.count("\n- ")
    struct = 0
    if bullets >= 3:
        struct += 2
    if re.search(r"(why|what|how)[^\n]{0,40}:?\n", low) or desc.count("\n\n") >= 4:
        struct += 1
    cat.checks.append(_chk("Structure & scannability", struct, 3, f"{bullets} bullet points." if bullets else "No bullet points.", "Use short sections and bullets (deliverables, why me, process)."))
    deliver = sum(w in low for w in ["deliver", "include", "you will get", "what you", "get", "receive", "what i provide", "services include", "what i can"])
    cat.checks.append(_chk("Deliverables", 2 if deliver >= 2 else (1 if deliver == 1 else 0), 2, "Deliverables are listed." if deliver >= 2 else "Deliverables are vague.", "List concrete outputs (files, workflows, pages, formats)."))
    trust = [w for w in TRUST_WORDS if w in low]
    cat.checks.append(_chk("Trust signals", min(2, len(trust) * 0.5), 2, f"Trust cues found: {', '.join(trust[:5]) or 'none'}.", "Mention testing, support period, revisions and process."))
    cta = [w for w in CTA_WORDS if w in low]
    cat.checks.append(_chk("Call to action", 1.5 if cta else 0, 1.5, "Clear call to action." if cta else "No call to action.", "End with one clear next step (e.g., 'Message me with your requirements')."))
    # hygiene
    urls = re.findall(r"https?://\S+", desc)
    typos = [t for t in KNOWN_TYPOS if re.search(r"\b" + t + r"\b", low)]
    dump = any(p.count(",") >= 12 for p in desc.split("\n"))
    pts, notes = 1.5, []
    if urls:
        pts -= 0.75
        notes.append(f"{len(urls)} external URLs (Fiverr may restrict external links — verify policy)")
    if dump:
        pts -= 0.75
        notes.append("comma-separated keyword dump (reads as keyword stuffing)")
    if typos:
        pts -= 0.5
        notes.append("typos: " + ", ".join(typos))
    cat.checks.append(_chk("Hygiene (links, stuffing, typos)", max(0, pts), 1.5, "; ".join(notes) or "Clean.",
                           "Remove external links and keyword dumps; fix typos." if notes else ""))
    return cat


def audit_keywords(title: str, desc: str, packages: list[dict], pk: str, meta: dict) -> CategoryResult:
    cat = CategoryResult("Keyword & tag relevance", WEIGHTS["Keyword & tag relevance"])
    pk_text = " ".join(p["title"] + " " + p["description"] for p in packages).lower()
    cons = (pk in title.lower()) + (pk in desc.lower()) + (pk in pk_text) if pk else 0
    cat.checks.append(_chk("Keyword consistency (title / description / packages)", cons / 3 * 5, 5,
                           f"Primary keyword '{pk}' appears in {cons}/3 areas.", "Repeat the primary keyword naturally in the title, description and package names."))
    n = count_phrase(desc, pk)
    ok = 2 <= n <= 6
    cat.checks.append(_chk("Keyword frequency (no stuffing)", 3 if ok else (1.5 if n == 1 or n == 7 else 0.5), 3,
                           f"'{pk}' used {n}× in the description.", "Use the primary keyword 2–4 times, naturally."))
    tags = [t.strip() for t in (meta.get("tags") or "").split(",") if t.strip()]
    if not tags:
        for nm, mx in [("Tag count", 4), ("Tag relevance", 6), ("Tag diversity", 4), ("Long-tail tags", 3), ("Commercial intent in tags", 3)]:
            cat.checks.append(_unknown(nm, mx, "Search tags are not exposed by the MCP.", "Enter your 5 search tags in Gig metadata to complete this check."))
        return cat
    cat.checks.append(_chk("Tag count", min(4, len(tags) / 5 * 4), 4, f"{len(tags)}/5 tags used.", "Use all 5 tag slots."))
    ref = set(content_tokens(title + " " + desc))
    rel = sum(any(w in ref for w in content_tokens(t)) for t in tags) / len(tags)
    cat.checks.append(_chk("Tag relevance", rel * 6, 6, f"{round(rel * 100)}% of tags match gig content.", "Replace tags that don't appear in your gig."))
    uniq = len({" ".join(sorted(content_tokens(t))) for t in tags}) / len(tags)
    cat.checks.append(_chk("Tag diversity", uniq * 4, 4, f"{round(uniq * 100)}% unique.", "Avoid near-duplicate tags."))
    lt = sum(len(t.split()) >= 2 for t in tags) / len(tags)
    cat.checks.append(_chk("Long-tail tags", lt * 3, 3, f"{round(lt * 100)}% multi-word tags.", "Use more 2–3 word phrases buyers actually type."))
    com = any(w in COMMERCIAL_WORDS for t in tags for w in content_tokens(t))
    cat.checks.append(_chk("Commercial intent in tags", 3 if com else 0, 3, "Includes buyer-intent terms." if com else "No buyer-intent terms.", "Add terms like 'developer', 'expert', 'setup', 'integration'."))
    return cat


def audit_metadata(gig: dict, title: str, desc: str, profile: dict, meta: dict) -> CategoryResult:
    cat = CategoryResult("Category & metadata relevance", WEIGHTS["Category & metadata relevance"])
    pk_text = " ".join(p["title"] + " " + p["description"] for p in gig["packages"])
    a, b = set(content_tokens(title)) - FILLER - ACTION_VERBS, set(content_tokens(pk_text + " " + desc[:300])) - FILLER
    overlap = len(a & b) / max(1, len(a))
    mism = overlap < 0.5
    cat.checks.append(_chk("Title ↔ packages/description alignment", 3 * min(1, overlap / 0.7), 3,
                           f"{round(overlap * 100)}% of title terms appear in packages/opening copy." + (" Title promises something the packages don't clearly deliver." if mism else ""),
                           "Make package names and descriptions mirror the service in the title."))
    prof = set(content_tokens(profile.get("title", "") + " " + profile.get("description", "")))
    gt = set(content_tokens(title + " " + desc[:400])) - FILLER - ACTION_VERBS
    pa = len(prof & gt) / max(1, len(gt))
    cat.checks.append(_chk("Fit with seller headline (portfolio coherence)", 3 if pa >= 0.2 else (1.5 if pa >= 0.1 else 0), 3,
                           f"{round(pa * 100)}% term overlap with your profile headline/bio.",
                           "Either update the headline to cover this service or treat this gig as a separate niche.", fixable=True))
    cat.checks.append(_chk("Gallery / preview present", 1 if gig.get("preview_url") else 0, 1, "Preview image present." if gig.get("preview_url") else "No preview image.", "Upload a clear thumbnail."))
    for nm, key, mx, nt in [("Category selected", "category", 2, "Category"), ("Subcategory selected", "subcategory", 1, "Subcategory")]:
        if meta.get(key):
            cat.checks.append(_chk(nm, mx, mx, f"{nt}: {meta[key]}."))
        else:
            cat.checks.append(_unknown(nm, mx, f"{nt} not exposed by the MCP.", "Enter it in Gig metadata."))
    faq = meta.get("faq_count")
    cat.checks.append(_chk("FAQs (3+ recommended)", min(2, (faq or 0) / 3 * 2), 2, f"{faq} FAQs.", "Add FAQs that answer pre-sale objections.") if faq is not None
                      else _unknown("FAQs", 2, "FAQs not exposed by the MCP.", "Enter the FAQ count in Gig metadata."))
    req = meta.get("requirements_count")
    cat.checks.append(_chk("Buyer requirements set", 1 if req else 0, 1, f"{req} requirement questions.", "Add requirement questions.") if req is not None
                      else _unknown("Buyer requirements", 1, "Requirements not exposed by the MCP.", "Enter the count in Gig metadata."))
    return cat


def audit_intent(desc: str, title: str) -> CategoryResult:
    cat = CategoryResult("Buyer intent & positioning", WEIGHTS["Buyer intent & positioning"])
    low = desc.lower()
    opening = low[:220]
    pain = any(p in opening for p in PAIN_OPENERS) or "?" in opening
    cat.checks.append(_chk("Opens with the buyer's problem", 3 if pain else 0.5, 3, "Opening speaks to a buyer need." if pain else "Opening talks about you rather than the buyer's problem.", "Open with the buyer's pain point or desired outcome."))
    ben = [w for w in BENEFIT_WORDS if w in low]
    cat.checks.append(_chk("Benefit language", min(2, len(ben) * 0.7), 2, f"Benefit cues: {', '.join(ben[:4]) or 'none'}.", "State outcomes: time saved, errors avoided, revenue protected."))
    nums = re.findall(r"\b\d+\b", desc)
    cat.checks.append(_chk("Specific, measurable details", 2 if len(nums) >= 3 else (1 if nums else 0), 2, f"{len(nums)} numbers/specifics.", "Add concrete numbers (fields, pages, days, hours)."))
    aud = [w for w in AUDIENCE_WORDS if w in low]
    cat.checks.append(_chk("Target audience named", 1.5 if aud else 0, 1.5, f"Audience cues: {', '.join(aud[:3]) or 'none'}.", "Name who it's for (e.g., WooCommerce store owners)."))
    generic = ["look no further", "top-notch", "welcome to my gig", "pesky", "attention to detail", "high-quality", "client-focused"]
    g = [x for x in generic if x in low]
    cat.checks.append(_chk("Specific, non-generic copy", 1.5 if not g else max(0, 1.5 - len(g) * 0.4), 1.5, "No generic filler phrases." if not g else "Generic phrases: " + ", ".join(g[:4]) + ".", "Replace generic phrases with specific proof and outcomes."))
    return cat


def audit_packages(gig: dict) -> CategoryResult:
    cat = CategoryResult("Packages & pricing clarity", WEIGHTS["Packages & pricing clarity"])
    pk = gig["packages"]
    cat.checks.append(_chk("Three tiers offered", 2 if len(pk) == 3 else 1, 2, f"{len(pk)} package tiers.", "Offer Basic / Standard / Premium."))
    prices = [p["price"] for p in pk if p["price"] is not None]
    inc = len(prices) >= 2 and all(prices[i] < prices[i + 1] for i in range(len(prices) - 1))
    ratio = (prices[-1] / prices[0]) if prices and prices[0] else 0
    cat.checks.append(_chk("Price ladder", 2 if inc and ratio >= 2 else (1 if inc else 0), 2,
                           f"${prices[0]:.0f} → ${prices[-1]:.0f} ({ratio:.1f}× spread)." if prices else "No prices.", "Create a clear step-up so Premium is a logical upsell."))
    good = sum(len(p["description"]) >= 40 for p in pk)
    cat.checks.append(_chk("Package descriptions are substantive", 2 * good / max(1, len(pk)), 2, f"{good}/{len(pk)} descriptions have enough detail.", "Describe exactly what each tier includes."))
    scope = sum(bool(re.search(r"\d", p["description"] + p["title"])) or any(w in (p["description"] + p["title"]).lower() for w in ["revision", "delivery", "day", "hour", "page"]) for p in pk)
    cat.checks.append(_chk("Scope, delivery & revisions stated", 2 * scope / max(1, len(pk)), 2,
                           f"{scope}/{len(pk)} tiers state numbers/limits. (Delivery time & revisions fields are not exposed by the MCP.)", "State quantity, delivery days and revisions in each package."))
    txt = " ".join(p["title"] + " " + p["description"] for p in pk).lower()
    typos = [t for t in KNOWN_TYPOS if re.search(r"\b" + t + r"\b", txt)]
    titles = [p["title"].lower().strip() for p in pk]
    distinct = len(set(titles)) == len(titles)
    sc = 2 - (1 if typos else 0) - (0.5 if not distinct else 0)
    cat.checks.append(_chk("Package naming quality", max(0, sc), 2, ("Typos: " + ", ".join(typos) + ". ") if typos else "No typos found. ", "Fix typos (e.g., 'Eliminator' → 'Elementor') and use distinct names."))
    return cat


def review_relevance(reviews: list[dict], terms: list[str]) -> tuple[int, int]:
    terms = [t for t in terms if len(t) > 3]
    hits = sum(any(t in r["text"].lower() for t in terms) for r in reviews)
    return hits, len(reviews)


def audit_trust(gig: dict, account: dict, terms: list[str], desc: str) -> CategoryResult:
    cat = CategoryResult("Trust signals & presentation", WEIGHTS["Trust signals & presentation"])
    rating = (account["profile"].get("rating") or {}).get("score") or 0
    cnt = (account["profile"].get("rating") or {}).get("count") or 0
    cat.checks.append(_chk("Seller rating", 2 if rating >= 4.8 else (1.5 if rating >= 4.6 else (1 if rating >= 4.3 else 0)), 2, f"Seller rating {rating}/5 (profile-level).", "Resolve root causes of low ratings; reply to negative reviews.", fixable=False))
    cat.checks.append(_chk("Review volume", 2 if cnt >= 50 else (1 if cnt >= 10 else 0), 2, f"{cnt} total reviews (profile-level).", "Ask satisfied buyers for reviews after delivery.", fixable=False))
    revs = account["reviews"]
    latest = max((r["date"] for r in revs), default="")
    d = days_since(latest) if latest else None
    rp = 0 if d is None else (2 if d <= 180 else (1 if d <= 365 else 0))
    cat.checks.append(_chk("Review recency", rp, 2, f"Newest review is {d} days old ({latest})." if d is not None else "No dated reviews.", "Run a review-request routine on every delivery; fresh reviews signal an active seller.", fixable=False))
    hits, tot = review_relevance(revs, terms)
    share = hits / tot if tot else 0
    cat.checks.append(_chk("Reviews relevant to this service (approx.)", 3 * min(1, share / 0.3), 3,
                           f"{hits}/{tot} loaded reviews mention this gig's topic terms. (Reviews are not linked to gigs by the MCP — keyword match only.)",
                           "Earn reviews that name this service; ask buyers to describe what you built.", fixable=False))
    proof = [w for w in ["tested", "testing", "guarantee", "support after", "money-back", "satisfaction"] if w in desc.lower()]
    cat.checks.append(_chk("Risk-reducers stated", min(1, len(proof) * 0.5), 1, f"Found: {', '.join(proof) or 'none'}.", "State testing, support and what's not included."))
    return cat


# ---- orchestration ----------------------------------------------------------------------------------------------
def audit_gig(gig: dict, account: dict, meta: dict | None = None) -> dict:
    meta = meta or {}
    title = (meta.get("title") or "").strip()
    verified = bool(title)
    if not title:
        title = gig["derived_title"]
    desc = gig["description"]
    pk = (meta.get("primary_keyword") or "").strip().lower() or infer_primary_keyword(title, desc)
    sec = secondary_terms(title, desc, gig["packages"])
    cats = [
        audit_title(title, pk, verified), audit_description(desc, title, pk, sec), audit_keywords(title, desc, gig["packages"], pk, meta),
        audit_metadata(gig, title, desc, account["profile"], meta), audit_intent(desc, title),
        audit_packages(gig), audit_trust(gig, account, [pk] + [t for t in sec[:4]], desc),
    ]
    total = sum(c.score for c in cats)
    full = sum(c.full_max for c in cats)
    conf = sum(c.verified_max for c in cats) / full if full else 0
    recs = []
    for c in cats:
        scale = c.weight / c.verified_max if c.verified_max else 0
        for k in c.checks:
            if k.status in ("warn", "fail") and k.fix:
                gain = (k.max - k.pts) * scale
                recs.append({"area": c.name, "check": k.name, "finding": k.note, "change": k.fix, "gain": round(gain, 1),
                              "fixable": k.fixable, "priority": "High" if gain >= 2 else ("Medium" if gain >= 1 else "Low"),
                              "benefit": f"Up to +{gain:.1f} audit points" + ("" if k.fixable else " (needs new orders/reviews, not an edit)")})
            elif k.status == "unknown":
                recs.append({"area": c.name, "check": k.name, "finding": k.note, "change": k.fix, "gain": 0.0, "fixable": True,
                              "priority": "Data", "benefit": "Completes the audit — missing input"})
    recs.sort(key=lambda r: (-r["gain"], r["area"]))
    fixable_gain = sum(r["gain"] for r in recs if r["fixable"] and r["priority"] != "Data")
    return {
        "slug": gig["slug"], "title": title, "title_verified": verified, "primary_keyword": pk, "secondary_terms": sec,
        "categories": cats, "total": round(total, 1), "confidence": round(conf, 2), "recommendations": recs,
        "projected": round(min(100, total + 0.75 * fixable_gain), 1),
        "weakest": sorted(cats, key=lambda c: c.score / c.weight)[:3],
    }


def audit_account(account: dict, all_meta: dict[str, dict]) -> list[dict]:
    return [audit_gig(g, account, all_meta.get(g["slug"])) for g in account["gigs"]]


def score_band(score: float) -> str:
    return "Excellent" if score >= 80 else ("Good" if score >= 65 else ("Needs Improvement" if score >= 45 else "Poor"))


def portfolio_clusters(account: dict) -> dict[str, list[str]]:
    """Group gigs by service family (for coherence analysis)."""
    fam = {"n8n / automation": ["n8n", "automation", "workflow", "automate"], "WordPress / WooCommerce": ["wordpress", "woocommerce", "wp", "elementor", "divi"],
           "PHP / web apps": ["php", "codeigniter", "mysql"], "Photo editing": ["photoshop", "background", "clipping"]}
    out: dict[str, list[str]] = {}
    for g in account["gigs"]:
        t = g["derived_title"].lower()
        placed = False
        for name, kws in fam.items():
            if name == "WordPress / WooCommerce" and any(k in t for k in ["n8n"]):
                continue
            if any(re.search(r"\b" + k + r"\b", t) for k in kws):
                out.setdefault(name, []).append(g["slug"])
                placed = True
                break
        if not placed:
            out.setdefault("Other", []).append(g["slug"])
    return out

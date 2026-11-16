"""Small text helpers shared by all engines."""
from __future__ import annotations
import html
import re
from collections import Counter

STOPWORDS = set("""a an and are as at be by for from has have i in into is it its me my of on or our so that the their them
this to up us we will with you your can do does any all more most other such than then there these those very just also
about over under out new get got make made using use used via per""".split())

ACTION_VERBS = {"build", "create", "develop", "design", "fix", "automate", "convert", "customize", "customise", "write", "setup",
                "set", "integrate", "connect", "optimize", "optimise", "analyze", "analyse", "do", "edit", "remove", "delete",
                "migrate", "debug", "repair", "install", "configure", "deliver", "research", "audit", "implement"}


def html_to_text(raw: str | None) -> str:
    """Convert Fiverr gig HTML into readable plain text (bullets become '- ')."""
    if not raw:
        return ""
    t = re.sub(r"(?i)<\s*br\s*/?>", "\n", raw)
    t = re.sub(r"(?i)</\s*(p|div|h\d|ul|ol)\s*>", "\n", t)
    t = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t).replace("\xa0", " ").replace("\r", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9+#.\-]*", (text or "").lower().replace("&", " and "))


def content_tokens(text: str) -> list[str]:
    return [t.strip(".-") for t in tokens(text) if t.strip(".-") and t.strip(".-") not in STOPWORDS and len(t.strip(".-")) > 1]


def ngrams(words: list[str], n: int) -> list[str]:
    return [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]


def title_from_slug(slug: str) -> str:
    """Fiverr slugs mirror the title at creation time. Titles are NOT exposed by the MCP, so this is a derived value."""
    words = (slug or "").replace("_", "-").split("-")
    return "I will " + " ".join(w for w in words if w)


def slug_from_url(url_or_slug: str) -> str:
    s = (url_or_slug or "").strip().split("?")[0].rstrip("/")
    return s.split("/")[-1] if "/" in s else s


def top_terms(text: str, n: int = 12) -> list[tuple[str, int]]:
    words = content_tokens(text)
    cnt = Counter(words)
    return cnt.most_common(n)


def count_phrase(text: str, phrase: str) -> int:
    if not phrase:
        return 0
    return len(re.findall(r"\b" + re.escape(phrase.lower()) + r"\b", (text or "").lower()))


def truncate(s: str, n: int = 80) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

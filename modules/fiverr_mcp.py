"""Fiverr MCP adapter (READ-ONLY).

Talks to Fiverr's public MCP server over Streamable HTTP (JSON-RPC 2.0). The connector is authless, so no
credentials are needed or stored. Every call is checked against READ_ONLY_TOOLS; this module cannot change
a live Fiverr gig. If the live server is unreachable, an offline snapshot of real MCP output is used and the
result is clearly labelled ``source = "snapshot"``.

Swap point: if you later get access to an authenticated/remote integration, implement a class with the same
public methods as ``FiverrMCPClient`` and return it from ``get_client()``.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from modules.text_utils import html_to_text, title_from_slug

DEFAULT_URL = "https://mcp.fiverr.com/mcp"
READ_ONLY_TOOLS = {
    "get_seller_profile", "list_seller_gigs", "get_seller_reviews_summary", "list_seller_reviews", "find_freelancers",
}
SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "data"


class MCPError(RuntimeError):
    pass


def _cfg(name: str, default: str = "") -> str:
    """Read config from env first, then Streamlit secrets (never hard-code secrets)."""
    if os.getenv(name):
        return os.environ[name]
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


class FiverrMCPClient:
    def __init__(self, url: str | None = None, timeout: int = 25):
        self.url = url or _cfg("FIVERR_MCP_URL", DEFAULT_URL)
        self.timeout = timeout
        self.session_id: str | None = None
        self._id = 0
        self.tools: list[dict] = []

    # ---- transport -------------------------------------------------------------------------------------------
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _parse(self, resp: requests.Response, req_id: int | None) -> dict:
        ctype = resp.headers.get("Content-Type", "")
        if "text/event-stream" in ctype:
            last = None
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    try:
                        msg = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    last = msg
                    if req_id is None or msg.get("id") == req_id:
                        return msg
            if last is not None:
                return last
            raise MCPError("Empty event-stream response from MCP server")
        try:
            return resp.json()
        except ValueError as e:
            raise MCPError(f"Non-JSON response from MCP server (HTTP {resp.status_code})") from e

    def _rpc(self, method: str, params: dict | None = None, notify: bool = False) -> dict:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        req_id = None
        if not notify:
            self._id += 1
            req_id = self._id
            payload["id"] = req_id
        try:
            resp = requests.post(self.url, headers=self._headers(), data=json.dumps(payload), timeout=self.timeout)
        except requests.RequestException as e:
            raise MCPError(f"Cannot reach Fiverr MCP server: {e.__class__.__name__}: {e}") from e
        if resp.status_code >= 400:
            raise MCPError(f"Fiverr MCP HTTP {resp.status_code}: {resp.text[:200]}")
        if "Mcp-Session-Id" in resp.headers:
            self.session_id = resp.headers["Mcp-Session-Id"]
        if notify:
            return {}
        msg = self._parse(resp, req_id)
        if "error" in msg:
            raise MCPError(f"MCP error: {msg['error']}")
        return msg.get("result", {})

    def initialize(self) -> None:
        self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "giggrowth-ai", "version": "1.0"}})
        self._rpc("notifications/initialized", {}, notify=True)

    def list_tools(self) -> list[dict]:
        if not self.session_id and not self.tools:
            self.initialize()
        self.tools = self._rpc("tools/list", {}).get("tools", [])
        return self.tools

    def call_tool(self, name: str, arguments: dict) -> Any:
        if name not in READ_ONLY_TOOLS:
            raise MCPError(f"Tool '{name}' is not on the read-only allow-list; refusing to call it.")
        if self.session_id is None:
            self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise MCPError(f"Tool {name} returned an error: {str(result.get('content'))[:300]}")
        if result.get("structuredContent"):
            return result["structuredContent"]
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        return parse_tool_text(text)

    # ---- typed helpers ---------------------------------------------------------------------------------------
    def get_profile(self, username: str) -> dict:
        return self.call_tool("get_seller_profile", {"username": username})

    def get_gigs(self, username: str) -> list[dict]:
        gigs, cursor = [], None
        for _ in range(10):
            args = {"username": username, "limit": 50}
            if cursor:
                args["end_cursor"] = cursor
            page = self.call_tool("list_seller_gigs", args)
            gigs += page.get("data", [])
            pg = page.get("pagination", {})
            if not pg.get("has_next_page"):
                break
            cursor = pg.get("end_cursor")
        return gigs

    def get_reviews_summary(self, username: str) -> dict:
        return self.call_tool("get_seller_reviews_summary", {"username": username})

    def get_reviews(self, username: str, max_pages: int = 3) -> list[dict]:
        out, cursor = [], None
        for _ in range(max_pages):
            args = {"username": username, "limit": 50, "sort_by": "recent"}
            if cursor:
                args["end_cursor"] = cursor
            page = self.call_tool("list_seller_reviews", args)
            out += page.get("data", [])
            pg = page.get("pagination", {})
            if not pg.get("has_next_page"):
                break
            cursor = pg.get("end_cursor")
        return out

    def find_sellers(self, brief: str, filters: dict | None = None) -> list[dict]:
        args: dict[str, Any] = {"brief": brief, "client_id": "giggrowth-ai"}
        if filters:
            args["filters"] = filters
        res = self.call_tool("find_freelancers", args)
        return res.get("sellers", []) if isinstance(res, dict) else []


def parse_tool_text(text: str) -> Any:
    """MCP tools return text. Some prefix prose before the JSON ('Found 5 sellers: ...{...}'); extract the JSON."""
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    for m in re.finditer(r"[\{\[]", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
            return obj
        except json.JSONDecodeError:
            continue
    return {"raw_text": text}


def get_client() -> FiverrMCPClient:
    return FiverrMCPClient()


# ---- normalisation (same code path for live data and the offline snapshot) ----------------------------------
def _money(p: dict | None) -> float | None:
    try:
        return float((p or {}).get("amount"))
    except (TypeError, ValueError):
        return None


def normalize_gig(raw: dict, username: str) -> dict:
    slug = raw.get("slug", "")
    html_desc = (raw.get("description") or {}).get("original", "")
    pk = []
    for p in raw.get("packages", []):
        pk.append({
            "tier": (p.get("type") or "").title(),
            "price": _money(p.get("price")),
            "currency": (p.get("price") or {}).get("currency", "USD"),
            "title": ((p.get("localized_title") or {}).get("original") or "").strip(),
            "description": ((p.get("localized_description") or {}).get("original") or "").strip(),
        })
    m = re.search(r"/gigs/(\d+)/", raw.get("preview_url", "") or "")
    return {
        "slug": slug, "gig_id": m.group(1) if m else None,
        "url": f"https://www.fiverr.com/{username}/{slug}",
        "derived_title": title_from_slug(slug),
        "description_html": html_desc, "description": html_to_text(html_desc),
        "packages": pk, "preview_url": raw.get("preview_url"),
    }


def normalize_review(r: dict) -> dict:
    return {"text": r.get("comment") or "", "score": r.get("score"), "date": (r.get("created_at") or "")[:10],
            "country": r.get("reviewer_country_code") or "", "has_seller_response": bool(r.get("seller_response"))}


def normalize_account(username: str, profile: dict, gigs: list[dict], summary: dict, reviews: list[dict]) -> dict:
    s = (summary or {}).get("user_buying_reviews", {})
    return {
        "username": username, "profile": profile,
        "gigs": [normalize_gig(g, username) for g in gigs],
        "reviews": [normalize_review(r) for r in reviews],
        "reviews_summary": {
            "average": s.get("average_valuation"), "count": s.get("total_reviews_count"),
            "communication": s.get("communication_valuation_average"), "service": s.get("service_valuation_average"),
            "recommend": s.get("recommend_valuation_average"),
        },
    }


def load_snapshot(username: str) -> dict | None:
    f = SNAPSHOT_DIR / f"snapshot_{username}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def load_account(username: str, prefer_live: bool = True) -> dict:
    """Return a normalised account dict with ``source`` ('live' | 'snapshot') and any warnings. Never fabricates."""
    username = (username or "").strip().strip("/").split("/")[-1]
    if not re.fullmatch(r"[A-Za-z0-9_\-]{2,40}", username):
        raise MCPError("Invalid Fiverr username.")
    warnings: list[str] = []
    if prefer_live:
        try:
            c = get_client()
            c.initialize()
            profile = c.get_profile(username)
            acct = normalize_account(username, profile, c.get_gigs(username), c.get_reviews_summary(username),
                                     c.get_reviews(username))
            acct.update(source="live", fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), warnings=warnings)
            return acct
        except MCPError as e:
            warnings.append(f"Live Fiverr MCP call failed: {e}")
    snap = load_snapshot(username)
    if snap is None:
        raise MCPError("; ".join(warnings) or "No live connection and no offline snapshot for this username.")
    acct = normalize_account(username, snap["profile"], snap["gigs"], snap["reviews_summary"], snap["reviews"])
    acct.update(source="snapshot", fetched_at=snap["meta"]["captured_at"], warnings=warnings,
                snapshot_note=snap["meta"].get("notes", ""))
    acct["competitor_sellers_snapshot"] = [s for b in snap.get("competitor_sellers", []) for s in b["sellers"]]
    return acct


def days_since(date_str: str) -> int | None:
    try:
        return (datetime.now(timezone.utc).date() - datetime.fromisoformat(date_str[:10]).date()).days
    except (ValueError, TypeError):
        return None


# What this connector can and cannot provide — shown in the UI so nothing is silently missing.
CAPABILITY_MATRIX = [
    ("Seller profile (name, country, languages, headline, bio, rating)", True, "get_seller_profile"),
    ("Published gigs: description, packages, prices, preview image, URL slug", True, "list_seller_gigs"),
    ("Review summary and review text", True, "get_seller_reviews_summary / list_seller_reviews"),
    ("Competitor seller discovery (skills, headline, rating, order count)", True, "find_freelancers (5 sellers per call)"),
    ("Exact gig title (only the URL slug is exposed)", False, "enter manually in Gig SEO Audit > Gig metadata"),
    ("Category / subcategory, search tags, FAQs, requirements", False, "enter manually in Gig SEO Audit > Gig metadata"),
    ("Delivery time and revisions per package", False, "not exposed; read only if written in package text"),
    ("Impressions, clicks, CTR, orders, revenue, conversion, cancellations", False, "import Fiverr analytics export (CSV/Excel)"),
    ("Historical analytics", False, "import CSV/Excel"),
    ("Inactive / paused / draft gigs", False, "only published gigs are returned"),
    ("Search rank position for a keyword", False, "log manual observations; no verified source"),
]

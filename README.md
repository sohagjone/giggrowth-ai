# GigGrowth AI – Fiverr SEO & Intelligence

A Streamlit app that audits your Fiverr gigs, researches keywords, analyses imported performance data, benchmarks competitors,
drafts titles/descriptions, and builds 7/30/60/90-day growth plans. **Read-only**: it cannot change a live gig.

## What is real, what is not (read this first)
| Capability | Source | Status |
|---|---|---|
| Profile, gigs (description, packages, prices), reviews | **Fiverr MCP** (`https://mcp.fiverr.com/mcp`, public, authless) | ✅ real data |
| Competitor sellers (skills, headline, rating, orders) | Fiverr MCP `find_freelancers` (5 per call) | ✅ real, seller-level |
| Exact title, category, tags, FAQs, requirements | not exposed by MCP | ✍️ enter manually (Gig SEO Audit → Gig metadata) |
| Impressions, clicks, orders, revenue, history | not exposed by MCP | 📥 import Fiverr analytics CSV/Excel |
| Search position | no verified source; scraping Fiverr is not done | ✍️ manual observations only; blank = "Not Available" |
| Keyword search volume / competition | does not exist publicly | ❌ never invented; qualitative opportunity only |
| SEO / health scores | internal rule-based audit | ⚠️ **not** Fiverr metrics |

The Fiverr MCP is a *public marketplace* connector keyed by username — it is not linked to your private seller dashboard. If
the live call fails (e.g., offline), the app uses `data/snapshot_<username>.json` (real MCP output captured 2026-11-14) and labels it **OFFLINE SNAPSHOT**.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional: set FIVERR_USERNAME and an LLM key
streamlit run app.py
```
Tests: `pip install pytest && python -m pytest -q tests`

## AI provider (optional)
Without a key every AI feature uses transparent rule-based generation (labelled). To enable an LLM set env vars or Streamlit secrets:
`LLM_PROVIDER=openai|anthropic`, `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, optional `LLM_MODEL`, `OPENAI_BASE_URL` (any OpenAI-compatible endpoint).
Keys are read server-side only and never rendered.

## MCP integration architecture
`modules/fiverr_mcp.py` speaks Streamable-HTTP JSON-RPC to the Fiverr MCP server, enforces a read-only tool allow-list, normalises results,
and falls back to the snapshot. The MCP used inside Claude is **not reachable from Streamlit Cloud**; this app therefore calls the same
*public* endpoint directly over HTTPS (no credentials). If you later get an authenticated/remote Fiverr integration, implement the same
methods (`get_profile`, `get_gigs`, `get_reviews`, `get_reviews_summary`, `find_sellers`) in a new client class and return it from `get_client()`;
put tokens in Streamlit secrets only.

## Push to GitHub
```bash
cd giggrowth-ai
git init -b main && git add . && git commit -m "GigGrowth AI"
git remote add origin https://github.com/<you>/giggrowth-ai.git
git push -u origin main
```
`.gitignore` already excludes `.env`, `.streamlit/secrets.toml` and the SQLite DB. Check `git status` shows no secret files before pushing.

## Deploy on Streamlit Community Cloud
1. Push the repo to GitHub (can be public — no secrets are in it).
2. https://share.streamlit.io → **Create app** → pick the repo, branch `main`, main file `app.py`.
3. **Advanced settings → Secrets**, paste (see `.streamlit/secrets.toml.example`):
```toml
FIVERR_USERNAME = "sohagjone"
LLM_PROVIDER = "openai"
OPENAI_API_KEY = "sk-..."
```
4. Deploy. Python 3.11+ recommended.

**Caveat:** Cloud storage is ephemeral — the SQLite file (metadata, imported analytics, rank log) resets on reboot. Re-import analytics after a restart,
or point `DB_PATH` at persistent storage / swap `db_manager.py` for a hosted database.

## Structure
`app.py` navigation · `pages/` 13 UI pages · `modules/` engines (MCP adapter, SEO, keywords, competitors, analytics, ranking, AI, strategy/health, reports) · `database/` SQLite · `data/` snapshot · `tests/`.

## Metric definitions
CTR = Clicks ÷ Impressions × 100 · Click→order = Orders ÷ Clicks × 100 · Impression→order = Orders ÷ Impressions × 100 · AOV = Revenue ÷ Orders. Zero denominators show "Not Available".

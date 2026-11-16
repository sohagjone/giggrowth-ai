"""SQLite persistence (gig metadata, rank observations, imported analytics, saved research).

NOTE: Streamlit Community Cloud's filesystem is ephemeral — data written here is lost on reboot/redeploy.
Use the export/import buttons (Settings) or point DB_PATH at a persistent volume / external DB for long-term history.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).resolve().parents[1] / "data" / "giggrowth.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS gig_meta (
  slug TEXT PRIMARY KEY, title TEXT, primary_keyword TEXT, tags TEXT, category TEXT, subcategory TEXT,
  faq_count INTEGER, requirements_count INTEGER, gallery_count INTEGER, has_video INTEGER, notes TEXT);
CREATE TABLE IF NOT EXISTS rank_obs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TEXT, gig_slug TEXT, keyword TEXT, position INTEGER,
  search_page INTEGER, category TEXT, location TEXT, context TEXT, competitors_ahead TEXT);
CREATE TABLE IF NOT EXISTS perf (
  id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, gig TEXT, impressions REAL, clicks REAL, orders REAL, revenue REAL);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
"""


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def get_meta(slug: str) -> dict:
    with conn() as c:
        r = c.execute("SELECT * FROM gig_meta WHERE slug=?", (slug,)).fetchone()
    return dict(r) if r else {}


def all_meta() -> dict[str, dict]:
    with conn() as c:
        return {r["slug"]: dict(r) for r in c.execute("SELECT * FROM gig_meta")}


def save_meta(slug: str, **f) -> None:
    keys = ["title", "primary_keyword", "tags", "category", "subcategory", "faq_count", "requirements_count",
            "gallery_count", "has_video", "notes"]
    vals = [f.get(k) for k in keys]
    with conn() as c:
        c.execute(f"INSERT INTO gig_meta (slug,{','.join(keys)}) VALUES (?,{','.join('?' * len(keys))}) "
                  f"ON CONFLICT(slug) DO UPDATE SET " + ",".join(f"{k}=excluded.{k}" for k in keys), [slug] + vals)


def add_rank_obs(row: dict) -> None:
    with conn() as c:
        c.execute("INSERT INTO rank_obs (observed_at,gig_slug,keyword,position,search_page,category,location,context,competitors_ahead)"
                  " VALUES (:observed_at,:gig_slug,:keyword,:position,:search_page,:category,:location,:context,:competitors_ahead)", row)


def rank_df() -> pd.DataFrame:
    with conn() as c:
        return pd.read_sql_query("SELECT * FROM rank_obs ORDER BY observed_at", c)


def delete_rank_obs(obs_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM rank_obs WHERE id=?", (obs_id,))


def save_perf(df: pd.DataFrame, replace: bool = True) -> int:
    with conn() as c:
        if replace:
            c.execute("DELETE FROM perf")
        d = df[["date", "gig", "impressions", "clicks", "orders", "revenue"]].copy()
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
        d.to_sql("perf", c, if_exists="append", index=False)
    return len(df)


def load_perf() -> pd.DataFrame:
    with conn() as c:
        df = pd.read_sql_query("SELECT date,gig,impressions,clicks,orders,revenue FROM perf", c)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def clear_perf() -> None:
    with conn() as c:
        c.execute("DELETE FROM perf")


def kv_get(key: str, default: str = "") -> str:
    with conn() as c:
        r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def kv_set(key: str, value: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO kv (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

"""News and social text ingestion.

Every source produces the same record shape and goes through one path
(`ingest_records`): clean → quality filter → exact de-duplication → asset
association → store. Sources are independent and switched on with the
NEWS_SOURCES setting, so one failing feed never blocks the others.

Sources
- cryptopanic_sample : bundled CC0 CryptoPanic dataset (BTC/ETH-tagged
                       headlines and posts, 2020 – 2 Dec 2025). Offline.
- csv                : your own CSV (published_at,title[,body,source,url,symbols]).
- rss                : public RSS feeds of crypto news sites. Only the latest
                       items, so history accumulates from the day you start.
- cryptopanic_api    : CryptoPanic developer API (needs CRYPTOPANIC_API_KEY).
- reddit             : Reddit app-only OAuth (needs REDDIT_CLIENT_ID/SECRET).
"""

from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import httpx
import pandas as pd

from app.config import ASSET_REGISTRY, SAMPLE_NEWS, settings
from app.db import IngestionLog, get_conn, utc_now
from app.services import http
from app.services.text_processing import (
    clean_text,
    content_hash,
    parse_utc,
    quality_issue,
    source_type_for,
    tag_assets,
    template_hash,
)

log = logging.getLogger("cryptosentinel.news")

TEMPLATE_KEEP_FIRST = 3  # a digit-stripped text repeated more often than this is a bot template


def ingest_records(records: Iterable[dict]) -> dict:
    """Stores normalised text records. Each dict needs: source, published_at,
    title. Optional: source_domain, source_type, external_id, body, url,
    tags (iterable of symbols supplied by the source), votes_positive/negative."""
    now = datetime.now(timezone.utc)
    stats = {"seen": 0, "inserted": 0, "duplicate": 0, "irrelevant": 0, "future_or_undated": 0, "excluded": 0}
    rows, links = [], []
    with get_conn() as conn:
        for rec in records:
            stats["seen"] += 1
            published = parse_utc(rec.get("published_at"))
            if published is None or published > now + timedelta(minutes=5):
                stats["future_or_undated"] += 1
                continue
            title = clean_text(rec.get("title"))
            body = clean_text(rec.get("body"))[:2000] or None
            text = title if not body else f"{title}. {body}"
            if not title:
                stats["future_or_undated"] += 1
                continue

            supplied = {t.strip().upper() for t in (rec.get("tags") or []) if t and t.strip()}
            tagged = supplied & set(ASSET_REGISTRY)
            if tagged:
                assets = {(s, "tag") for s in tagged}
            else:
                assets = {(s, "keyword") for s in tag_assets(text)}
            if not assets:
                stats["irrelevant"] += 1
                continue

            chash = content_hash(title)
            if conn.execute("SELECT 1 FROM text_records WHERE content_hash = ?", (chash,)).fetchone():
                stats["duplicate"] += 1
                continue
            issue = quality_issue(title)
            if issue:
                stats["excluded"] += 1
            domain = rec.get("source_domain")
            cur = conn.execute(
                """INSERT OR IGNORE INTO text_records(source, source_domain, source_type, external_id, published_at,
                       published_date, title, body, clean_text, url, votes_positive, votes_negative,
                       content_hash, template_hash, excluded_reason, collected_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec["source"], domain, rec.get("source_type") or source_type_for(domain),
                    str(rec["external_id"]) if rec.get("external_id") is not None else None,
                    published.strftime("%Y-%m-%dT%H:%M:%SZ"), published.strftime("%Y-%m-%d"),
                    title, body, text, rec.get("url"),
                    rec.get("votes_positive"), rec.get("votes_negative"),
                    chash, template_hash(title), issue, utc_now(),
                ),
            )
            if cur.rowcount == 0:
                stats["duplicate"] += 1
                continue
            stats["inserted"] += 1
            links.extend((cur.lastrowid, symbol, method) for symbol, method in assets)
        conn.executemany("INSERT OR IGNORE INTO text_assets(text_id, symbol, method) VALUES (?,?,?)", links)
    flag_bot_templates()
    return stats


def flag_bot_templates() -> int:
    """Causal bot filter: within each template key, posts after the first
    TEMPLATE_KEEP_FIRST (by publication time) are excluded. Only earlier posts
    are counted, so the filter never uses information from the future."""
    with get_conn() as conn:
        cur = conn.execute(
            f"""UPDATE text_records SET excluded_reason = 'bot_template'
                WHERE excluded_reason IS NULL AND id IN (
                  SELECT id FROM (
                    SELECT id, ROW_NUMBER() OVER (PARTITION BY template_hash ORDER BY published_at, id) AS rn
                    FROM text_records
                  ) WHERE rn > {TEMPLATE_KEEP_FIRST}
                )"""
        )
        return cur.rowcount


# ── Sources ────────────────────────────────────────────────────────────────

def load_sample_news(path: Path | str = SAMPLE_NEWS) -> dict:
    with IngestionLog("text", "cryptopanic_sample") as entry:
        df = pd.read_csv(path)
        df = df.sort_values("published_at")
        entry.n_fetched = len(df)
        records = (
            {
                "source": "cryptopanic_sample",
                "source_domain": r.source_domain if isinstance(r.source_domain, str) else None,
                "external_id": r.source_id,
                "published_at": r.published_at,
                "title": r.title,
                "url": r.url if isinstance(r.url, str) else None,
                "tags": str(r.tags).split(",") if isinstance(r.tags, str) else [],
                "votes_positive": int(r.votes_positive),
                "votes_negative": int(r.votes_negative),
            }
            for r in df.itertuples(index=False)
        )
        stats = ingest_records(records)
        entry.n_inserted = stats["inserted"]
        entry.message = _summary(stats)
    return stats


def import_text_csv(path: Path | str, source_name: str = "csv") -> dict:
    """Imports a user CSV. Required: published_at (UTC), title. Optional: body,
    source (domain), url, symbols (comma list, e.g. "BTC,ETH"), source_type."""
    with IngestionLog("text", f"csv:{Path(path).name}") as entry:
        df = pd.read_csv(path)
        missing = {"published_at", "title"} - set(df.columns)
        if missing:
            raise ValueError(f"text CSV is missing columns: {sorted(missing)}")
        entry.n_fetched = len(df)
        df = df.astype(object).where(df.notna(), None)
        records = (
            {
                "source": source_name,
                "source_domain": row.get("source"),
                "source_type": row.get("source_type") if row.get("source_type") in ("news", "social") else None,
                "external_id": row.get("id"),
                "published_at": row["published_at"],
                "title": row["title"],
                "body": row.get("body"),
                "url": row.get("url"),
                "tags": str(row["symbols"]).split(",") if row.get("symbols") else [],
            }
            for row in df.to_dict("records")
        )
        stats = ingest_records(records)
        entry.n_inserted = stats["inserted"]
        entry.message = _summary(stats)
    return stats


def fetch_rss(feed_url: str) -> list[dict]:
    import feedparser

    xml = http.get(feed_url, expect="text", ttl=600)
    parsed = feedparser.parse(xml)
    if parsed.bozo and not parsed.entries:
        raise http.ProviderError(f"could not parse feed {feed_url}")
    domain = urlparse(feed_url).netloc.removeprefix("www.")
    out = []
    for e in parsed.entries:
        stamp = e.get("published_parsed") or e.get("updated_parsed")
        if not stamp:
            continue
        out.append(
            {
                "source": f"rss:{domain}",
                "source_domain": domain,
                "source_type": "news",
                "external_id": e.get("id") or e.get("link"),
                "published_at": datetime.fromtimestamp(calendar.timegm(stamp), tz=timezone.utc),
                "title": e.get("title"),
                "body": e.get("summary"),
                "url": e.get("link"),
            }
        )
    return out


def fetch_cryptopanic_api() -> list[dict]:
    if not settings.cryptopanic_api_key:
        raise http.ProviderError("CRYPTOPANIC_API_KEY is not set")
    data = http.get(
        "https://cryptopanic.com/api/developer/v2/posts/",
        params={
            "auth_token": settings.cryptopanic_api_key,
            "currencies": ",".join(settings.assets),
            "public": "true",
        },
        ttl=600,
    )
    out = []
    for item in (data or {}).get("results", []):
        codes = [c.get("code") for c in (item.get("instruments") or item.get("currencies") or []) if c.get("code")]
        source = item.get("source") or {}
        out.append(
            {
                "source": "cryptopanic_api",
                "source_domain": source.get("domain"),
                "external_id": item.get("id"),
                "published_at": item.get("published_at") or item.get("created_at"),
                "title": item.get("title"),
                "body": item.get("description"),
                "url": item.get("original_url") or item.get("url"),
                "tags": codes,
            }
        )
    return out


def fetch_reddit() -> list[dict]:
    """Reddit's API requires OAuth. This uses app-only (client credentials)
    access, which Reddit permits for read-only use of public listings."""
    if not (settings.reddit_client_id and settings.reddit_client_secret):
        raise http.ProviderError("REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are not set")
    with httpx.Client(timeout=settings.http_timeout) as client:
        token_resp = client.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            headers={"User-Agent": http.USER_AGENT},
        )
        if token_resp.status_code != 200:
            raise http.ProviderError(f"Reddit auth failed (HTTP {token_resp.status_code})")
        token = token_resp.json().get("access_token")
    out = []
    for sub in settings.reddit_subreddits:
        data = http.get(
            f"https://oauth.reddit.com/r/{sub}/new",
            params={"limit": "100"},
            headers={"Authorization": f"bearer {token}"},
            ttl=600,
        )
        for child in (data or {}).get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("stickied") or post.get("over_18"):
                continue
            out.append(
                {
                    "source": f"reddit:r/{sub}",
                    "source_domain": "reddit.com",
                    "source_type": "social",
                    "external_id": post.get("name"),
                    "published_at": datetime.fromtimestamp(float(post.get("created_utc", 0)), tz=timezone.utc),
                    "title": post.get("title"),
                    "body": (post.get("selftext") or "")[:1000],
                    "url": f"https://www.reddit.com{post.get('permalink', '')}",
                }
            )
    return out


def refresh_live_text() -> dict[str, dict]:
    """Runs every enabled live source independently and reports per source."""
    report: dict[str, dict] = {}
    jobs: list[tuple[str, callable]] = []
    for name in settings.news_sources:
        if name == "rss":
            jobs.extend((f"rss:{urlparse(u).netloc.removeprefix('www.')}", (lambda u=u: fetch_rss(u))) for u in settings.rss_feeds)
        elif name == "cryptopanic_api":
            jobs.append(("cryptopanic_api", fetch_cryptopanic_api))
        elif name == "reddit":
            jobs.append(("reddit", fetch_reddit))
    for label, job in jobs:
        try:
            with IngestionLog("text", label) as entry:
                records = job()
                entry.n_fetched = len(records)
                stats = ingest_records(records)
                entry.n_inserted = stats["inserted"]
                entry.message = _summary(stats)
            report[label] = {"ok": True, **stats}
        except Exception as exc:  # noqa: BLE001
            report[label] = {"ok": False, "error": str(exc)}
            log.warning("text source %s failed: %s", label, exc)
    return report


def _summary(stats: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in stats.items())

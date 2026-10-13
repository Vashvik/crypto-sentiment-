from datetime import datetime, timedelta, timezone

from app.db import get_conn
from app.services.news_ingestion import TEMPLATE_KEEP_FIRST, ingest_records


def _rec(title, minutes=0, **kw):
    base = datetime(2024, 3, 1, 12, tzinfo=timezone.utc) + timedelta(minutes=minutes)
    return {"source": "test", "published_at": base.isoformat(), "title": title, **kw}


def test_dedupe_relevance_future_and_tags(temp_db):
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    stats = ingest_records([
        _rec("Bitcoin climbs after strong ETF inflows"),
        _rec("bitcoin climbs after strong ETF inflows!"),             # duplicate after normalisation
        _rec("Gold prices steady as dollar weakens today"),            # no supported asset
        {"source": "test", "published_at": future, "title": "Bitcoin will moon tomorrow for sure"},
        _rec("Market update for the week ahead traders", tags=["ETH"]),  # tagged by source
    ])
    assert stats["inserted"] == 2 and stats["duplicate"] == 1
    assert stats["irrelevant"] == 1 and stats["future_or_undated"] == 1
    with get_conn() as conn:
        links = {(r["symbol"], r["method"]) for r in conn.execute("SELECT symbol, method FROM text_assets")}
    assert links == {("BTC", "keyword"), ("ETH", "tag")}


def test_bot_template_filter_is_causal(temp_db):
    posts = [_rec(f"{100 + i} #BTC transferred from unknown wallet to exchange", minutes=i) for i in range(6)]
    ingest_records(posts)
    with get_conn() as conn:
        rows = conn.execute("SELECT excluded_reason FROM text_records ORDER BY published_at").fetchall()
    reasons = [r["excluded_reason"] for r in rows]
    assert reasons[:TEMPLATE_KEEP_FIRST] == [None] * TEMPLATE_KEEP_FIRST
    assert all(r == "bot_template" for r in reasons[TEMPLATE_KEEP_FIRST:])

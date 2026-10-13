"""SQLite storage. One file, no server, created on first use.

Raw text, per-text sentiment scores and daily aggregates live in separate
tables, and forecasts are append-only (realised returns are filled in later,
never overwritten), so every number on the dashboard can be traced back."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.config import ASSET_REGISTRY, settings

_db_path: Path = settings.database_path
_init_lock = threading.Lock()
_initialised: set[str] = set()

MIGRATIONS: list[str] = [
    # 1 — initial schema
    """
    CREATE TABLE IF NOT EXISTS assets (
        symbol TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        coingecko_id TEXT,
        binance_symbol TEXT,
        active INTEGER NOT NULL DEFAULT 1
    );

    -- One row per asset, UTC day and source. Daily bars are only stored for
    -- completed UTC days; the running day is never written.
    CREATE TABLE IF NOT EXISTS market_prices (
        symbol TEXT NOT NULL REFERENCES assets(symbol),
        date TEXT NOT NULL,              -- YYYY-MM-DD, UTC day the bar closes
        open REAL, high REAL, low REAL,
        close REAL NOT NULL,
        volume_usd REAL,
        market_cap_usd REAL,
        source TEXT NOT NULL,            -- coinmetrics_sample | coingecko | binance | csv
        fetched_at TEXT NOT NULL,
        UNIQUE (symbol, date, source)
    );
    CREATE INDEX IF NOT EXISTS ix_prices_symbol_date ON market_prices(symbol, date);

    CREATE TABLE IF NOT EXISTS text_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,            -- e.g. cryptopanic_sample, rss:cointelegraph.com
        source_domain TEXT,
        source_type TEXT NOT NULL,       -- news | social
        external_id TEXT,
        published_at TEXT NOT NULL,      -- ISO-8601 UTC
        published_date TEXT NOT NULL,    -- UTC day used for aggregation
        title TEXT NOT NULL,
        body TEXT,
        clean_text TEXT NOT NULL,
        url TEXT,
        votes_positive INTEGER,
        votes_negative INTEGER,
        content_hash TEXT NOT NULL UNIQUE,   -- exact duplicate guard
        template_hash TEXT NOT NULL,         -- digits stripped, for bot-template detection
        excluded_reason TEXT,                -- NULL = eligible
        collected_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_text_date ON text_records(published_date);
    CREATE INDEX IF NOT EXISTS ix_text_template ON text_records(template_hash);
    CREATE UNIQUE INDEX IF NOT EXISTS ux_text_source_ext ON text_records(source, external_id)
        WHERE external_id IS NOT NULL;

    CREATE TABLE IF NOT EXISTS text_assets (
        text_id INTEGER NOT NULL REFERENCES text_records(id) ON DELETE CASCADE,
        symbol TEXT NOT NULL REFERENCES assets(symbol),
        method TEXT NOT NULL,            -- tag (provided by source) | keyword
        UNIQUE (text_id, symbol)
    );
    CREATE INDEX IF NOT EXISTS ix_text_assets_symbol ON text_assets(symbol);

    CREATE TABLE IF NOT EXISTS sentiment_scores (
        text_id INTEGER NOT NULL REFERENCES text_records(id) ON DELETE CASCADE,
        engine TEXT NOT NULL,
        score REAL NOT NULL,             -- [-1, 1]
        p_pos REAL, p_neu REAL, p_neg REAL,
        label TEXT NOT NULL,             -- positive | neutral | negative
        scored_at TEXT NOT NULL,
        UNIQUE (text_id, engine)
    );

    CREATE TABLE IF NOT EXISTS daily_sentiment (
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        engine TEXT NOT NULL,
        n_records INTEGER NOT NULL,
        n_news INTEGER NOT NULL,
        n_social INTEGER NOT NULL,
        sent_mean REAL,                  -- NULL when n_records = 0 (missing, not neutral)
        sent_std REAL,
        pos_prop REAL, neu_prop REAL, neg_prop REAL,
        sent_news REAL, sent_social REAL,
        computed_at TEXT NOT NULL,
        UNIQUE (symbol, date, engine)
    );

    CREATE TABLE IF NOT EXISTS feature_snapshots (
        run_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        date TEXT NOT NULL,
        features_json TEXT NOT NULL,
        UNIQUE (run_id, symbol, date)
    );

    CREATE TABLE IF NOT EXISTS model_runs (
        run_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL,            -- running | completed | failed
        data_mode TEXT NOT NULL,
        engine TEXT NOT NULL,
        config_json TEXT NOT NULL,
        summary_json TEXT,
        message TEXT
    );

    -- Per (run, asset, horizon) evaluation results
    CREATE TABLE IF NOT EXISTS model_evaluations (
        run_id TEXT NOT NULL REFERENCES model_runs(run_id),
        symbol TEXT NOT NULL,
        horizon INTEGER NOT NULL,
        selected_model TEXT,
        data_start TEXT, data_end TEXT,
        metrics_json TEXT NOT NULL,
        UNIQUE (run_id, symbol, horizon)
    );

    -- Walk-forward out-of-sample predictions (validation + test segments)
    CREATE TABLE IF NOT EXISTS backtest_predictions (
        run_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        horizon INTEGER NOT NULL,
        model_name TEXT NOT NULL,
        date TEXT NOT NULL,              -- feature date t (prediction made at close of t)
        segment TEXT NOT NULL,           -- validation | test
        regime TEXT,                     -- high_vol | low_vol
        y_true REAL NOT NULL,
        y_pred REAL NOT NULL,
        UNIQUE (run_id, symbol, horizon, model_name, date)
    );
    CREATE INDEX IF NOT EXISTS ix_bt_lookup ON backtest_predictions(run_id, symbol, horizon);

    -- Forward-looking forecasts. Append-only.
    CREATE TABLE IF NOT EXISTS forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        horizon INTEGER NOT NULL,
        model_name TEXT NOT NULL,
        is_primary INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        feature_date TEXT NOT NULL,      -- data cutoff: close of this UTC day
        target_date TEXT NOT NULL,
        reference_price REAL NOT NULL,
        predicted_return REAL NOT NULL,
        lower_return REAL, upper_return REAL,
        interval_note TEXT,
        contributions_json TEXT,
        sentiment_available INTEGER NOT NULL,
        realized_return REAL,
        realized_at TEXT,
        UNIQUE (run_id, symbol, horizon, model_name, feature_date)
    );
    CREATE INDEX IF NOT EXISTS ix_forecasts_lookup ON forecasts(symbol, horizon, created_at);

    CREATE TABLE IF NOT EXISTS sentiment_engine_evaluations (
        evaluated_at TEXT NOT NULL,
        engine TEXT NOT NULL,
        segment TEXT NOT NULL,           -- validation | test
        n INTEGER NOT NULL,
        metrics_json TEXT NOT NULL,
        UNIQUE (engine, segment)
    );

    CREATE TABLE IF NOT EXISTS ingestion_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,              -- market | text | sentiment | aggregate | train
        source TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,            -- ok | error | skipped
        n_fetched INTEGER DEFAULT 0,
        n_inserted INTEGER DEFAULT 0,
        message TEXT
    );

    CREATE TABLE IF NOT EXISTS app_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def set_database_path(path: Path | str) -> None:
    """Used by tests and the CLI to point at a different file."""
    global _db_path
    _db_path = Path(path)


def database_path() -> Path:
    return _db_path


def _connect() -> sqlite3.Connection:
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db() -> None:
    key = str(_db_path)
    with _init_lock:
        conn = _connect()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            current = row["v"] or 0
            for version, sql in enumerate(MIGRATIONS, start=1):
                if version > current:
                    conn.executescript(sql)
                    conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
            for asset in ASSET_REGISTRY.values():
                conn.execute(
                    """INSERT INTO assets(symbol, name, coingecko_id, binance_symbol, active)
                       VALUES (?,?,?,?,1)
                       ON CONFLICT(symbol) DO UPDATE SET name=excluded.name,
                         coingecko_id=excluded.coingecko_id, binance_symbol=excluded.binance_symbol""",
                    (asset.symbol, asset.name, asset.coingecko_id, asset.binance_symbol),
                )
            conn.commit()
            _initialised.add(key)
        finally:
            conn.close()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    if str(_db_path) not in _initialised:
        init_db()
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_state(key: str, default: str | None = None) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_state(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO app_state(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


class IngestionLog:
    """Context manager that records one ingestion/training step in ingestion_log."""

    def __init__(self, kind: str, source: str):
        self.kind, self.source = kind, source
        self.n_fetched = 0
        self.n_inserted = 0
        self.message: str | None = None
        self.status = "ok"
        self._id: int | None = None

    def __enter__(self) -> "IngestionLog":
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO ingestion_log(kind, source, started_at, status) VALUES (?,?,?,?)",
                (self.kind, self.source, utc_now(), "running"),
            )
            self._id = cur.lastrowid
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc is not None:
            self.status = "error"
            self.message = f"{type(exc).__name__}: {exc}"[:500]
        with get_conn() as conn:
            conn.execute(
                """UPDATE ingestion_log SET finished_at=?, status=?, n_fetched=?, n_inserted=?, message=?
                   WHERE id=?""",
                (utc_now(), self.status, self.n_fetched, self.n_inserted, self.message, self._id),
            )
        return False  # never swallow

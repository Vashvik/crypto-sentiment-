"""Cryptocurrency market data.

Daily convention used everywhere in this project: a "day" is a UTC calendar
day, and the close of day D is the price at 00:00 UTC on D+1 (end of D).
Providers are normalised to that convention before anything is stored, and
the running (incomplete) UTC day is never stored.

Providers
- coinmetrics_sample : bundled Coin Metrics community CSV (BTC, ETH). Offline.
- coingecko          : free public API, no key needed (optional demo key).
                       Close, volume and market cap; last 365 days.
- binance            : public market-data mirror (data-api.binance.vision),
                       no key. Full OHLCV in USDT, up to 1000 days.
- csv                : user-supplied CSV with date,symbol,close[,open,high,low,volume_usd,market_cap_usd].
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import ASSET_REGISTRY, SAMPLE_PRICES, settings
from app.db import IngestionLog, get_conn, utc_now
from app.services import http

log = logging.getLogger("cryptosentinel.market")

PRICE_COLUMNS = ["date", "open", "high", "low", "close", "volume_usd", "market_cap_usd"]

# Which source wins when several cover the same day. The bundled history is
# preferred where it exists so the long series stays on one methodology; live
# providers extend it forward. CoinGecko (cross-exchange) is preferred over a
# single exchange (Binance). The series builder takes, per day, the
# highest-priority source that has a value, and reports where it switches.
SOURCE_PRIORITY = {"csv": 0, "coinmetrics_sample": 1, "coingecko": 2, "binance": 3}


def last_completed_utc_day(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=1)).date()


# ── Providers ───────────────────────────────────────────────────────────────

def fetch_coingecko(symbol: str, days: int = 365) -> pd.DataFrame:
    asset = ASSET_REGISTRY[symbol]
    headers = {"x-cg-demo-api-key": settings.coingecko_api_key} if settings.coingecko_api_key else None
    data = http.get(
        f"https://api.coingecko.com/api/v3/coins/{asset.coingecko_id}/market_chart",
        params={"vs_currency": "usd", "days": str(min(days, 365)), "interval": "daily"},
        headers=headers,
        ttl=900,
    )
    return normalise_coingecko(data)


def normalise_coingecko(data: dict) -> pd.DataFrame:
    """CoinGecko daily points sit at 00:00 UTC; that instant is the close of the
    previous UTC day. The final point is 'now' (a partial day) and is dropped."""
    if not isinstance(data, dict) or not data.get("prices"):
        raise http.ProviderError("CoinGecko returned no price data")

    def frame(key: str, col: str) -> pd.DataFrame:
        rows = data.get(key) or []
        df = pd.DataFrame(rows, columns=["ts", col])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df

    df = frame("prices", "close")
    df = df.merge(frame("total_volumes", "volume_usd"), on="ts", how="left")
    df = df.merge(frame("market_caps", "market_cap_usd"), on="ts", how="left")
    on_midnight = (df["ts"].dt.hour == 0) & (df["ts"].dt.minute == 0)
    df = df[on_midnight].copy()
    df["date"] = (df["ts"] - pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    df = df.drop_duplicates("date", keep="last")
    for col in ("open", "high", "low"):
        df[col] = np.nan
    return _finalise(df)


def fetch_binance(symbol: str, limit: int = 1000) -> pd.DataFrame:
    asset = ASSET_REGISTRY[symbol]
    data = http.get(
        "https://data-api.binance.vision/api/v3/klines",
        params={"symbol": asset.binance_symbol, "interval": "1d", "limit": str(min(limit, 1000))},
        ttl=900,
    )
    return normalise_binance(data)


def normalise_binance(rows: list) -> pd.DataFrame:
    """Binance 1d klines open at 00:00 UTC, so a candle's date is its UTC day.
    The still-open candle (close time in the future) is dropped. Volume is the
    quote volume in USDT, used as a USD proxy."""
    if not isinstance(rows, list) or not rows:
        raise http.ProviderError("Binance returned no klines")
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    records = []
    for r in rows:
        open_ms, o, h, l, c, _base_vol, close_ms, quote_vol = r[:8]
        if close_ms > now_ms:
            continue
        records.append(
            {
                "date": datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                "open": float(o), "high": float(h), "low": float(l), "close": float(c),
                "volume_usd": float(quote_vol), "market_cap_usd": np.nan,
            }
        )
    return _finalise(pd.DataFrame.from_records(records))


def load_price_csv(path: Path | str, source: str = "csv") -> dict[str, pd.DataFrame]:
    """Reads a long CSV (date,symbol,close,...) into per-symbol frames."""
    raw = pd.read_csv(path)
    missing = {"date", "symbol", "close"} - set(raw.columns)
    if missing:
        raise ValueError(f"price CSV is missing columns: {sorted(missing)}")
    out = {}
    for symbol, group in raw.groupby(raw["symbol"].str.upper()):
        if symbol not in ASSET_REGISTRY:
            continue
        g = group.copy()
        for col in PRICE_COLUMNS:
            if col not in g:
                g[col] = np.nan
        out[symbol] = _finalise(g)
    return out


def _finalise(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], utc=False).dt.strftime("%Y-%m-%d")
    for col in PRICE_COLUMNS[1:]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df = df[np.isfinite(df["close"]) & (df["close"] > 0)]
    # Only completed UTC days
    df = df[df["date"] <= last_completed_utc_day().isoformat()]
    return df[PRICE_COLUMNS].drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


# ── Storage ────────────────────────────────────────────────────────────────

def store_prices(symbol: str, df: pd.DataFrame, source: str) -> int:
    if df.empty:
        return 0
    fetched = utc_now()
    rows = [
        (
            symbol, r.date,
            _none(r.open), _none(r.high), _none(r.low), float(r.close),
            _none(r.volume_usd), _none(r.market_cap_usd), source, fetched,
        )
        for r in df.itertuples(index=False)
    ]
    with get_conn() as conn:
        before = conn.total_changes
        conn.executemany(
            """INSERT INTO market_prices(symbol,date,open,high,low,close,volume_usd,market_cap_usd,source,fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(symbol,date,source) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                 volume_usd=excluded.volume_usd, market_cap_usd=excluded.market_cap_usd,
                 fetched_at=excluded.fetched_at""",
            rows,
        )
        return conn.total_changes - before


def _none(value) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def load_sample_prices() -> int:
    total = 0
    with IngestionLog("market", "coinmetrics_sample") as entry:
        frames = load_price_csv(SAMPLE_PRICES)
        for symbol, df in frames.items():
            entry.n_fetched += len(df)
            total += store_prices(symbol, df, "coinmetrics_sample")
        entry.n_inserted = total
    return total


def refresh_live_prices(symbols: list[str] | None = None) -> dict[str, dict]:
    """Fetches each asset from the configured providers in order, stopping at
    the first that succeeds. Returns a per-asset status report; failures are
    recorded, never raised, so one bad provider cannot take the app down."""
    report: dict[str, dict] = {}
    for symbol in symbols or list(settings.assets):
        report[symbol] = {"ok": False, "errors": []}
        for provider in settings.market_providers:
            fetch = {"coingecko": fetch_coingecko, "binance": fetch_binance}.get(provider)
            if fetch is None:
                continue
            try:
                with IngestionLog("market", f"{provider}:{symbol}") as entry:
                    df = fetch(symbol)
                    entry.n_fetched = len(df)
                    entry.n_inserted = store_prices(symbol, df, provider)
                report[symbol] = {"ok": True, "provider": provider, "rows": len(df),
                                  "last_date": df["date"].iloc[-1] if len(df) else None,
                                  "errors": report[symbol]["errors"]}
                break
            except Exception as exc:  # noqa: BLE001 — provider failures are data, not crashes
                report[symbol]["errors"].append(f"{provider}: {exc}")
                log.warning("market refresh failed for %s via %s: %s", symbol, provider, exc)
    return report


# ── Reading ────────────────────────────────────────────────────────────────

def price_series(symbol: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """One clean daily series per asset on a complete calendar index. Days no
    source covers stay NaN (never forward-filled), so a gap can never be
    mistaken for a zero return."""
    query = "SELECT * FROM market_prices WHERE symbol = ?"
    params: list = [symbol]
    if start:
        query += " AND date >= ?"; params.append(start)
    if end:
        query += " AND date <= ?"; params.append(end)
    with get_conn() as conn:
        raw = pd.read_sql_query(query, conn, params=params)
    if raw.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS + ["source"]).set_index(pd.DatetimeIndex([], name="date"))
    raw["priority"] = raw["source"].map(SOURCE_PRIORITY).fillna(9)
    raw = raw.sort_values(["date", "priority"]).drop_duplicates("date", keep="first")
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.set_index("date")
    full = pd.date_range(raw.index.min(), raw.index.max(), freq="D", name="date")
    return raw.reindex(full)[PRICE_COLUMNS[1:] + ["source"]]


def coverage() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT symbol, source, MIN(date) AS first, MAX(date) AS last, COUNT(*) AS n,
                      MAX(fetched_at) AS fetched_at
               FROM market_prices GROUP BY symbol, source ORDER BY symbol, source"""
        ).fetchall()
    return [dict(r) for r in rows]

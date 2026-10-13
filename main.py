"""CryptoSentinel API (FastAPI).

All routes live under /api/v1 and return JSON. Errors use FastAPI's standard
shape: {"detail": "..."}; unexpected failures never expose a stack trace.
Slow work (live ingestion, training) runs as a background job guarded by a
process-wide lock, so dashboard requests only ever read the database."""

from __future__ import annotations

import json
import logging
import re
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date

import numpy as np
import pandas as pd
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import ASSET_REGISTRY, HORIZONS, settings
from app.db import get_conn, get_state, init_db
from app.services import forecasting, http, pipeline, sentiment
from app.services.aggregation import daily_sentiment
from app.services.forecasting import CANDIDATE_BY_NAME
from app.services.market_data import coverage as price_coverage
from app.services.market_data import price_series

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cryptosentinel.api")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(lifespan=lifespan, title="CryptoSentinel API", version=forecasting.CODE_VERSION,
              description="Aggregated daily sentiment and short-term crypto return forecasts (research use only).")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Job-Token"],
)

JOB_TOKEN = os.getenv("JOB_TOKEN", "").strip()
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DISCLAIMER = "Academic research output. Not investment advice; forecasts are uncertain and can be wrong."


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):  # pragma: no cover - safety net
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. Check the backend log for details."})


# ── Validation helpers ─────────────────────────────────────────────────────

def _symbol(symbol: str) -> str:
    s = symbol.upper().strip()
    if s not in ASSET_REGISTRY:
        raise HTTPException(404, f"Unknown asset '{symbol}'. Supported: {', '.join(ASSET_REGISTRY)}")
    return s


def _date(value: str | None, name: str) -> str | None:
    if value is None or value == "":
        return None
    if not _DATE.match(value):
        raise HTTPException(422, f"{name} must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, f"{name} is not a valid date") from None
    return value


def _range(start: str | None, end: str | None) -> tuple[str | None, str | None]:
    s, e = _date(start, "start"), _date(end, "end")
    if s and e and s > e:
        raise HTTPException(422, "start must be on or before end")
    return s, e


def _horizon(h: int) -> int:
    if h not in HORIZONS:
        raise HTTPException(422, f"horizon must be one of {list(HORIZONS)}")
    return h


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def _latest_run_id() -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT run_id FROM model_runs WHERE status='completed' ORDER BY created_at DESC LIMIT 1").fetchone()
    return row["run_id"] if row else None


def _check_job_token(token: str | None) -> None:
    if JOB_TOKEN and not (token and secrets.compare_digest(token, JOB_TOKEN)):
        raise HTTPException(401, "This deployment requires an X-Job-Token header to start jobs.")


# ── Health & status ────────────────────────────────────────────────────────

@app.get("/health")
@app.get("/api/v1/health")
def health():
    return {"status": "ok", "version": forecasting.CODE_VERSION, "data_mode": settings.data_mode}


@app.get("/api/v1/status")
def status():
    with get_conn() as conn:
        text_cov = conn.execute(
            """SELECT ta.symbol, MIN(t.published_date) AS first, MAX(t.published_date) AS last, COUNT(*) AS n
               FROM text_records t JOIN text_assets ta ON ta.text_id = t.id
               WHERE t.excluded_reason IS NULL GROUP BY ta.symbol"""
        ).fetchall()
        excluded = conn.execute(
            "SELECT COALESCE(excluded_reason, 'eligible') AS reason, COUNT(*) AS n FROM text_records GROUP BY 1"
        ).fetchall()
        last_by_source = conn.execute(
            """SELECT l.kind, l.source, l.status, l.started_at, l.finished_at, l.n_fetched, l.n_inserted, l.message
               FROM ingestion_log l JOIN (SELECT kind, source, MAX(id) AS id FROM ingestion_log GROUP BY kind, source) m
               ON m.id = l.id ORDER BY l.kind, l.source"""
        ).fetchall()
        last_ok = conn.execute(
            "SELECT kind, MAX(finished_at) AS at FROM ingestion_log WHERE status='ok' GROUP BY kind"
        ).fetchall()
        run = conn.execute(
            "SELECT run_id, created_at, status, engine, data_mode, message FROM model_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    engine_sel = get_state("sentiment_engine_selection")
    return {
        "data_mode": settings.data_mode,
        "data_mode_note": (
            "Sample mode: bundled historical data only (Coin Metrics prices, CryptoPanic headlines to 2 Dec 2025). Nothing here is live."
            if settings.data_mode == "sample"
            else "Live mode: bundled history extended with live CoinGecko/Binance prices and the enabled news sources."
        ),
        "assets_configured": list(settings.assets),
        "price_coverage": [dict(r) for r in price_coverage()],
        "text_coverage": [dict(r) for r in text_cov],
        "text_quality": [dict(r) for r in excluded],
        "sources": [dict(r) for r in last_by_source],
        "last_success": {r["kind"]: r["at"] for r in last_ok},
        "sentiment_engine": sentiment.active_engine(),
        "sentiment_engine_selection": json.loads(engine_sel) if engine_sel else None,
        "latest_model_run": dict(run) if run else None,
        "pipeline": pipeline.status(),
        "training_in_progress": forecasting.is_training(),
        "disclaimer": DISCLAIMER,
    }


# ── Assets & market data ───────────────────────────────────────────────────

@app.get("/api/v1/assets")
def assets():
    out = []
    for symbol in settings.assets:
        a = ASSET_REGISTRY[symbol]
        prices = price_series(symbol)
        closes = prices["close"].dropna() if not prices.empty else pd.Series(dtype=float)
        item = {"symbol": symbol, "name": a.name, "has_data": bool(len(closes))}
        if len(closes):
            last_date = closes.index[-1]
            prev = prices["close"].get(last_date - pd.Timedelta(days=1))
            item.update({
                "last_date": last_date.strftime("%Y-%m-%d"),
                "last_close": float(closes.iloc[-1]),
                "change_1d": float(closes.iloc[-1] / prev - 1) if prev is not None and pd.notna(prev) else None,
                "first_date": closes.index[0].strftime("%Y-%m-%d"),
                "n_days": int(len(closes)),
                "source": prices["source"].dropna().iloc[-1],
                "volume_usd": _clean(prices["volume_usd"].iloc[-1]),
                "market_cap_usd": _clean(prices["market_cap_usd"].iloc[-1]),
            })
        out.append(item)
    return {"assets": out, "data_mode": settings.data_mode}


@app.get("/api/v1/market/{symbol}")
def market(symbol: str, start: str | None = None, end: str | None = None):
    symbol = _symbol(symbol)
    start, end = _range(start, end)
    full = price_series(symbol)
    if full.empty:
        raise HTTPException(404, f"No price data stored for {symbol}. Run the pipeline or a live refresh first.")
    full["return_1d"] = full["close"] / full["close"].shift(1) - 1  # computed before slicing so the first row is correct
    df = full.loc[start:end] if (start or end) else full
    df = df.reset_index()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return {
        "symbol": symbol,
        "timezone": "UTC (close = end of the UTC day)",
        "rows": _records(df[["date", "open", "high", "low", "close", "volume_usd", "market_cap_usd", "return_1d", "source"]]),
        "missing_days": int(df["close"].isna().sum()),
        "data_mode": settings.data_mode,
    }


@app.get("/api/v1/market/quotes/live")
@limiter.limit("30/minute")
def live_quotes(request: Request):
    """Real-time spot prices from CoinGecko. Only in live mode; clearly
    separate from the daily-close series used by the model."""
    if settings.data_mode != "live":
        return {"available": False, "reason": "Live quotes are disabled in sample mode (DATA_MODE=sample).", "quotes": []}
    ids = ",".join(ASSET_REGISTRY[s].coingecko_id for s in settings.assets)
    try:
        headers = {"x-cg-demo-api-key": settings.coingecko_api_key} if settings.coingecko_api_key else None
        data = http.get("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true", "include_last_updated_at": "true"},
                        headers=headers, ttl=60)
    except http.ProviderError as exc:
        return {"available": False, "reason": str(exc), "quotes": []}
    quotes = []
    for s in settings.assets:
        q = data.get(ASSET_REGISTRY[s].coingecko_id) or {}
        if "usd" in q:
            quotes.append({"symbol": s, "price": q["usd"], "change_24h_pct": q.get("usd_24h_change"),
                           "last_updated_at": q.get("last_updated_at"), "source": "CoinGecko"})
    return {"available": bool(quotes), "quotes": quotes, "attribution": "Price data by CoinGecko"}


# ── Sentiment ──────────────────────────────────────────────────────────────

@app.get("/api/v1/sentiment/{symbol}/daily")
def sentiment_daily(symbol: str, start: str | None = None, end: str | None = None):
    symbol = _symbol(symbol)
    start, end = _range(start, end)
    engine = sentiment.active_engine()
    ds = daily_sentiment(symbol, engine, start, end)
    prices = price_series(symbol)
    if not prices.empty:
        p = prices.copy()
        p["return_1d"] = p["close"] / p["close"].shift(1) - 1
        p["return_next_1d"] = p["return_1d"].shift(-1)
        p = p.reset_index()
        p["date"] = p["date"].dt.strftime("%Y-%m-%d")
        ds = ds.merge(p[["date", "close", "return_1d", "return_next_1d"]], on="date", how="left")
    cols = [c for c in ["date", "n_records", "n_news", "n_social", "sent_mean", "sent_std", "pos_prop", "neu_prop", "neg_prop",
                        "sent_news", "sent_social", "close", "return_1d", "return_next_1d"] if c in ds]
    corr = None
    if len(ds) and "return_next_1d" in ds:
        both = ds[["sent_mean", "return_1d", "return_next_1d"]].dropna()
        if len(both) >= 30:
            corr = {
                "same_day": float(both["sent_mean"].corr(both["return_1d"])),
                "next_day": float(both["sent_mean"].corr(both["return_next_1d"])),
                "n": int(len(both)),
                "note": "Pearson correlation of daily sentiment with that day's return and with the next day's return, over the selected range. Descriptive only.",
            }
    return {"symbol": symbol, "engine": engine, "rows": _records(ds[cols]) if len(ds) else [], "correlation": corr,
            "missing_note": "Days with n_records = 0 have no sentiment value (missing, not neutral)."}


@app.get("/api/v1/sentiment/{symbol}/sources")
def sentiment_sources(symbol: str, start: str | None = None, end: str | None = None):
    symbol = _symbol(symbol)
    start, end = _range(start, end)
    engine = sentiment.active_engine()
    q = """SELECT t.source_type, COALESCE(t.source_domain, t.source) AS domain, COUNT(*) AS n, AVG(s.score) AS mean_score
           FROM text_records t JOIN text_assets ta ON ta.text_id = t.id
           JOIN sentiment_scores s ON s.text_id = t.id AND s.engine = ?
           WHERE ta.symbol = ? AND t.excluded_reason IS NULL"""
    params: list = [engine, symbol]
    if start:
        q += " AND t.published_date >= ?"; params.append(start)
    if end:
        q += " AND t.published_date <= ?"; params.append(end)
    q += " GROUP BY 1, 2 ORDER BY n DESC"
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    by_type: dict[str, dict] = {}
    for r in rows:
        t = by_type.setdefault(r["source_type"], {"source_type": r["source_type"], "n": 0, "score_sum": 0.0})
        t["n"] += r["n"]; t["score_sum"] += r["mean_score"] * r["n"]
    types = [{"source_type": k, "n": v["n"], "mean_score": v["score_sum"] / v["n"] if v["n"] else None} for k, v in by_type.items()]
    return {"symbol": symbol, "engine": engine, "by_type": types, "by_domain": rows[:15]}


@app.get("/api/v1/sentiment/{symbol}/records")
def sentiment_records(symbol: str, day: str = Query(..., description="UTC day YYYY-MM-DD"), limit: int = Query(50, ge=1, le=200)):
    symbol = _symbol(symbol)
    day = _date(day, "day")
    engine = sentiment.active_engine()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT t.published_at, t.title, t.source_type, COALESCE(t.source_domain, t.source) AS domain, t.url,
                      s.score, s.label, ta.method AS asset_link
               FROM text_records t JOIN text_assets ta ON ta.text_id = t.id
               JOIN sentiment_scores s ON s.text_id = t.id AND s.engine = ?
               WHERE ta.symbol = ? AND t.published_date = ? AND t.excluded_reason IS NULL
               ORDER BY t.published_at LIMIT ?""",
            (engine, symbol, day, limit),
        ).fetchall()
    return {"symbol": symbol, "day": day, "engine": engine, "records": [dict(r) for r in rows]}


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=3, max_length=1000)
    engine: str | None = Field(None, pattern="^(vader|vader_crypto|crypto_lr|finbert)$")


@app.post("/api/v1/sentiment/analyze")
@limiter.limit("30/minute")
def sentiment_analyze(request: Request, body: AnalyzeRequest):
    try:
        return sentiment.score_single(body.text, body.engine)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/api/v1/sentiment/engines")
def sentiment_engines():
    with get_conn() as conn:
        rows = conn.execute("SELECT engine, segment, n, metrics_json, evaluated_at FROM sentiment_engine_evaluations").fetchall()
    engines: dict[str, dict] = {}
    for r in rows:
        engines.setdefault(r["engine"], {})[r["segment"]] = json.loads(r["metrics_json"])
    sel = get_state("sentiment_engine_selection")
    meta = get_state("crypto_lr_meta")
    return {"active": sentiment.active_engine(), "configured": settings.sentiment_engine,
            "selection": json.loads(sel) if sel else None, "engines": engines,
            "crypto_lr_training": json.loads(meta) if meta else None,
            "label_definition": "Community votes on CryptoPanic: positive if ≥2 positive votes and at least twice the negative votes; negative the other way round; other headlines unlabelled."}


# ── Forecasts & models ─────────────────────────────────────────────────────

@app.get("/api/v1/forecasts/{symbol}/latest")
def forecast_latest(symbol: str):
    symbol = _symbol(symbol)
    run_id = _latest_run_id()
    if not run_id:
        raise HTTPException(404, "No trained model yet. Run the pipeline (python scripts/pipeline.py all).")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM forecasts WHERE run_id = ? AND symbol = ? ORDER BY horizon, is_primary DESC, model_name",
            (run_id, symbol),
        ).fetchall()
        evals = {r["horizon"]: json.loads(r["metrics_json"]) for r in conn.execute(
            "SELECT horizon, metrics_json FROM model_evaluations WHERE run_id = ? AND symbol = ?", (run_id, symbol)).fetchall()}
    if not rows:
        raise HTTPException(404, f"The latest model run has no forecast for {symbol} (not enough data for this asset).")
    horizons: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        d["contributions"] = json.loads(d.pop("contributions_json")) if d.get("contributions_json") else None
        d["label"] = CANDIDATE_BY_NAME[d["model_name"]].label
        d["predicted_price"] = d["reference_price"] * (1 + d["predicted_return"])
        d["validation_rmse"] = evals.get(d["horizon"], {}).get("models", {}).get(d["model_name"], {}).get("validation", {}).get("rmse")
        d["test_rmse"] = evals.get(d["horizon"], {}).get("models", {}).get(d["model_name"], {}).get("test", {}).get("rmse")
        h = horizons.setdefault(str(d["horizon"]), {"horizon": d["horizon"], "primary": None, "models": []})
        if d["is_primary"]:
            h["primary"] = d
        h["models"].append(d)
    return {"symbol": symbol, "run_id": run_id, "horizons": horizons, "disclaimer": DISCLAIMER,
            "selection_rule": "Primary model = lowest validation RMSE in walk-forward evaluation (baselines included)."}


@app.get("/api/v1/forecasts/{symbol}/history")
def forecast_history(symbol: str, horizon: int = 1, limit: int = Query(100, ge=1, le=1000)):
    symbol = _symbol(symbol)
    horizon = _horizon(horizon)
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT run_id, model_name, created_at, feature_date, target_date, reference_price, predicted_return,
                      lower_return, upper_return, realized_return, realized_at, sentiment_available
               FROM forecasts WHERE symbol = ? AND horizon = ? AND is_primary = 1
               ORDER BY created_at DESC LIMIT ?""",
            (symbol, horizon, limit),
        ).fetchall()
    return {"symbol": symbol, "horizon": horizon, "forecasts": [dict(r) for r in rows]}


@app.get("/api/v1/backtest/{symbol}")
def backtest(symbol: str, horizon: int = 1, models: str | None = None):
    symbol = _symbol(symbol)
    horizon = _horizon(horizon)
    run_id = _latest_run_id()
    if not run_id:
        raise HTTPException(404, "No trained model yet.")
    wanted = [m for m in (models or "").split(",") if m in CANDIDATE_BY_NAME] or None
    q = "SELECT model_name, date, segment, regime, y_true, y_pred FROM backtest_predictions WHERE run_id=? AND symbol=? AND horizon=?"
    params: list = [run_id, symbol, horizon]
    if wanted:
        q += " AND model_name IN (%s)" % ",".join("?" * len(wanted)); params += wanted
    with get_conn() as conn:
        df = pd.read_sql_query(q + " ORDER BY date", conn, params=params)
    if df.empty:
        return {"symbol": symbol, "horizon": horizon, "run_id": run_id, "rows": []}
    wide = df.pivot(index="date", columns="model_name", values="y_pred")
    meta = df.drop_duplicates("date").set_index("date")[["segment", "regime", "y_true"]].rename(columns={"y_true": "actual"})
    wide = meta.join(wide).reset_index()
    return {"symbol": symbol, "horizon": horizon, "run_id": run_id, "models": sorted(df["model_name"].unique()),
            "rows": _records(wide), "note": "Out-of-sample walk-forward predictions; each row was predicted by a model trained only on data available before that date."}


@app.get("/api/v1/models/performance")
def model_performance(symbol: str, horizon: int = 1):
    symbol = _symbol(symbol)
    horizon = _horizon(horizon)
    run_id = _latest_run_id()
    if not run_id:
        raise HTTPException(404, "No trained model yet.")
    with get_conn() as conn:
        ev = conn.execute("SELECT * FROM model_evaluations WHERE run_id=? AND symbol=? AND horizon=?", (run_id, symbol, horizon)).fetchone()
        run = conn.execute("SELECT config_json, summary_json, created_at, engine FROM model_runs WHERE run_id=?", (run_id,)).fetchone()
    if not ev:
        raise HTTPException(404, f"No evaluation for {symbol} at horizon {horizon} in the latest run.")
    summary = json.loads(run["summary_json"] or "{}").get("assets", {}).get(symbol, {})
    return {
        "symbol": symbol, "horizon": horizon, "run_id": run_id, "created_at": run["created_at"], "engine": run["engine"],
        "config": json.loads(run["config_json"]), "evaluation": json.loads(ev["metrics_json"]),
        "data_start": ev["data_start"], "data_end": ev["data_end"],
        "coverage": {k: summary.get(k) for k in ("price_days", "sentiment_days", "sentiment_coverage", "price_sources")},
        "granger": summary.get("granger", []),
        "notes": {
            "dm_sign": "Diebold–Mariano statistic on squared errors: negative = the sentiment model was more accurate, positive = less accurate.",
            "granger": "Granger tests ask whether lagged values add predictive information. They do not show economic causation.",
        },
    }


@app.get("/api/v1/models/runs")
def model_runs(limit: int = Query(20, ge=1, le=100)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT run_id, created_at, status, data_mode, engine, message FROM model_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"runs": [dict(r) for r in rows]}


# ── Jobs ───────────────────────────────────────────────────────────────────

def _start(background: BackgroundTasks, steps: list[str], live: bool | None) -> dict:
    if pipeline.is_running():
        raise HTTPException(409, "A pipeline job is already running. Check /api/v1/jobs/status.")
    background.add_task(pipeline.run, steps, live)
    return {"started": True, "steps": steps}


@app.post("/api/v1/jobs/refresh")
@limiter.limit("6/hour")
def job_refresh(request: Request, background: BackgroundTasks, x_job_token: str | None = Header(None)):
    """Fetch live prices and news, score, aggregate, fill realised returns."""
    _check_job_token(x_job_token)
    if settings.data_mode != "live":
        raise HTTPException(409, "Live refresh is disabled in sample mode. Set DATA_MODE=live in backend/.env.")
    return _start(background, ["refresh-live", "score", "aggregate", "realize"], True)


@app.post("/api/v1/jobs/train")
@limiter.limit("4/hour")
def job_train(request: Request, background: BackgroundTasks, x_job_token: str | None = Header(None)):
    """Re-score, re-aggregate, retrain, re-evaluate and forecast (takes a few minutes)."""
    _check_job_token(x_job_token)
    return _start(background, ["score", "aggregate", "train", "realize"], False)


@app.get("/api/v1/jobs/status")
def job_status():
    return pipeline.status()

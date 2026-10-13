"""End-to-end pipeline: ingest → score → aggregate → train/evaluate → forecast.

Used by the CLI (scripts/pipeline.py) and the API's background jobs. A single
process-wide lock prevents overlapping runs (duplicate ingestion, two
trainings writing at once)."""

from __future__ import annotations

import json
import logging
import threading
import time

from app.config import settings
from app.db import get_state, init_db, set_state, utc_now
from app.services import aggregation, forecasting, market_data, news_ingestion, sentiment

log = logging.getLogger("cryptosentinel.pipeline")
_lock = threading.Lock()

STEPS = ("load-sample", "refresh-live", "train-text-model", "evaluate-engines", "score", "aggregate", "train", "realize")


def is_running() -> bool:
    return _lock.locked()


def run(steps: list[str] | None = None, live: bool | None = None, engine: str | None = None) -> dict:
    if not _lock.acquire(blocking=False):
        raise RuntimeError("the pipeline is already running")
    started = time.time()
    steps = steps or list(STEPS)
    live = settings.data_mode == "live" if live is None else live
    report: dict = {"started_at": utc_now(), "steps": {}, "live": live}
    set_state("pipeline_status", json.dumps({"running": True, "started_at": report["started_at"], "steps": steps}))
    try:
        init_db()
        if "load-sample" in steps:
            report["steps"]["load-sample"] = {
                "prices_upserted": market_data.load_sample_prices(),
                "text": news_ingestion.load_sample_news(),
            }
        if "refresh-live" in steps and live:
            report["steps"]["refresh-live"] = {
                "market": market_data.refresh_live_prices(),
                "text": news_ingestion.refresh_live_text(),
            }
        if "train-text-model" in steps:
            report["steps"]["train-text-model"] = sentiment.train_crypto_lr()
        if "evaluate-engines" in steps:
            report["steps"]["evaluate-engines"] = sentiment.evaluate_engines()
        chosen = engine or sentiment.active_engine()
        report["engine"] = chosen
        if "score" in steps:
            report["steps"]["score"] = {"scored": sentiment.score_pending(chosen)}
        if "aggregate" in steps:
            report["steps"]["aggregate"] = {"rows": aggregation.aggregate(chosen)}
        if "train" in steps:
            report["steps"]["train"] = forecasting.train_and_forecast(chosen)
        if "realize" in steps:
            report["steps"]["realize"] = {"updated": forecasting.update_realized_returns()}
        report["status"] = "completed"
    except Exception as exc:
        log.exception("pipeline failed")
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["finished_at"] = utc_now()
        report["seconds"] = round(time.time() - started, 1)
        set_state("pipeline_status", json.dumps({"running": False, "last": _brief(report)}, default=str))
        _lock.release()
    return report


def _brief(report: dict) -> dict:
    return {k: report.get(k) for k in ("started_at", "finished_at", "seconds", "status", "error", "engine", "live")} | {
        "steps": list(report.get("steps", {}).keys())
    }


def status() -> dict:
    raw = get_state("pipeline_status")
    data = json.loads(raw) if raw else {"running": False, "last": None}
    data["running"] = is_running()
    return data

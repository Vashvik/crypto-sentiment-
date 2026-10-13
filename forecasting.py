"""Model training, walk-forward evaluation, model selection and forecasts.

Design
- Six candidates per asset and horizon: zero-return and historical-mean
  baselines, Ridge and gradient boosting each with market-only features and
  with market + sentiment features. The two feature sets differ ONLY in the
  sentiment columns, so their comparison is the ablation.
- Walk-forward, expanding window, refit every REFIT_EVERY_DAYS. For a block
  starting at day s, training uses rows t ≤ s − h only (the target of row t
  needs the close of t + h, which is known at s only if t + h ≤ s). This
  embargo stops overlapping 3-day targets leaking into training.
- Imputation (training medians + missing indicators) and scaling are fitted
  inside each pipeline on the training rows of that refit only.
- Out-of-sample predictions before VALIDATION_END form the validation segment
  (used to pick the model); later ones form the test segment (reported only).
- The model with the lowest validation RMSE becomes the primary model, even
  if that is a baseline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.config import HORIZONS, settings
from app.db import get_conn, utc_now
from app.services.evaluation import diebold_mariano, forecast_metrics, granger_hac, volatility_regime
from app.services.features import FEATURE_SETS, MARKET_FEATURES, SENTIMENT_FEATURES, build_dataset

log = logging.getLogger("cryptosentinel.forecasting")

CODE_VERSION = "1.0.0"
REQUIRED_MARKET = ["ret_1", "ret_lag2", "mom_20", "vol_30"]  # rows lacking these are still warming up
_train_lock = threading.Lock()


@dataclass(frozen=True)
class Candidate:
    name: str
    label: str
    kind: str          # zero | mean | ridge | gbr
    feature_set: str | None

    def build(self, seed: int):
        if self.kind == "ridge":
            return Pipeline([
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", RidgeCV(alphas=np.logspace(-1, 4, 30))),
            ])
        if self.kind == "gbr":
            return Pipeline([
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", GradientBoostingRegressor(
                    loss="huber", n_estimators=150, max_depth=2, learning_rate=0.03,
                    subsample=0.8, min_samples_leaf=20, random_state=seed,
                )),
            ])
        return None


CANDIDATES = [
    Candidate("zero", "Zero-return baseline", "zero", None),
    Candidate("hist_mean", "Historical-mean baseline", "mean", None),
    Candidate("ridge_market", "Ridge · market only", "ridge", "market"),
    Candidate("ridge_sentiment", "Ridge · market + sentiment", "ridge", "market_sentiment"),
    Candidate("gbr_market", "Gradient boosting · market only", "gbr", "market"),
    Candidate("gbr_sentiment", "Gradient boosting · market + sentiment", "gbr", "market_sentiment"),
]
CANDIDATE_BY_NAME = {c.name: c for c in CANDIDATES}
ABLATION_PAIRS = [("ridge_sentiment", "ridge_market"), ("gbr_sentiment", "gbr_market")]


def is_training() -> bool:
    return _train_lock.locked()


# ── Core: walk-forward for one asset / horizon ─────────────────────────────

def _fit_predict(cand: Candidate, train: pd.DataFrame, test: pd.DataFrame, target: str, seed: int):
    if cand.kind == "zero":
        return np.zeros(len(test)), None
    if cand.kind == "mean":
        return np.full(len(test), float(train[target].mean())), None
    cols = FEATURE_SETS[cand.feature_set]
    model = cand.build(seed)
    model.fit(train[cols], train[target])
    return model.predict(test[cols]), model


def walk_forward(data: pd.DataFrame, horizon: int, seed: int) -> pd.DataFrame:
    target = f"target_{horizon}"
    usable = data.dropna(subset=REQUIRED_MARKET)
    labelled = usable.dropna(subset=[target])
    if labelled.empty:
        return pd.DataFrame()
    first_oos = labelled.index.min() + timedelta(days=settings.min_train_days)
    oos_dates = labelled.index[labelled.index >= first_oos]
    if len(oos_dates) == 0:
        return pd.DataFrame()
    rows = []
    block_start = first_oos
    while block_start <= oos_dates.max():
        block_end = block_start + timedelta(days=settings.refit_every)
        test = labelled[(labelled.index >= block_start) & (labelled.index < block_end)]
        train = labelled[labelled.index <= block_start - timedelta(days=horizon)]
        if len(test) and len(train) >= 200:
            for cand in CANDIDATES:
                preds, _ = _fit_predict(cand, train, test, target, seed)
                bench = float(train[target].mean())
                for date, y, p in zip(test.index, test[target], preds):
                    rows.append({"date": date, "model_name": cand.name, "y_true": float(y), "y_pred": float(p), "bench": bench})
        block_start = block_end
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["segment"] = np.where(out["date"] <= pd.Timestamp(settings.validation_end), "validation", "test")
    regime = volatility_regime(data["vol_30"])
    out["regime"] = out["date"].map(regime)
    return out


def summarise(bt: pd.DataFrame, horizon: int) -> dict:
    """Metrics per model × segment (+ per regime), ablation DM tests, selection."""
    summary: dict = {"models": {}, "ablation": {}, "regimes": {}}
    for name, g in bt.groupby("model_name"):
        summary["models"][name] = {"label": CANDIDATE_BY_NAME[name].label}
        for seg, gs in g.groupby("segment"):
            summary["models"][name][seg] = forecast_metrics(gs["y_true"].to_numpy(), gs["y_pred"].to_numpy(), gs["bench"].to_numpy())
            for reg, gr in gs.groupby("regime"):
                summary["regimes"].setdefault(seg, {}).setdefault(reg, {})[name] = forecast_metrics(
                    gr["y_true"].to_numpy(), gr["y_pred"].to_numpy(), gr["bench"].to_numpy()
                )
    wide_err = bt.assign(err=bt["y_true"] - bt["y_pred"]).pivot_table(index=["segment", "date"], columns="model_name", values="err")
    for seg in ("validation", "test"):
        if seg not in wide_err.index.get_level_values(0):
            continue
        w = wide_err.loc[seg]
        for with_sent, without in ABLATION_PAIRS:
            pair = w[[with_sent, without]].dropna()
            res = diebold_mariano(pair[with_sent].to_numpy(), pair[without].to_numpy(), horizon)
            res["rmse_with_sentiment"] = float(np.sqrt(np.mean(pair[with_sent] ** 2)))
            res["rmse_market_only"] = float(np.sqrt(np.mean(pair[without] ** 2)))
            summary["ablation"].setdefault(seg, {})[f"{with_sent}_vs_{without}"] = res
            # ablation within regimes
            reg = bt[(bt["segment"] == seg)].drop_duplicates("date").set_index("date")["regime"]
            for regime_name in ("high_vol", "low_vol"):
                idx = reg[reg == regime_name].index.intersection(pair.index)
                if len(idx) >= 30:
                    r = diebold_mariano(pair.loc[idx, with_sent].to_numpy(), pair.loc[idx, without].to_numpy(), horizon)
                    summary["ablation"][seg][f"{with_sent}_vs_{without}:{regime_name}"] = r
    val = {n: m["validation"]["rmse"] for n, m in summary["models"].items() if "validation" in m}
    summary["selected_model"] = min(val, key=val.get) if val else "hist_mean"
    summary["selection_rule"] = "lowest RMSE on the validation segment (walk-forward, out-of-sample)"
    return summary


# ── Final fit, latest forecast, contributions ──────────────────────────────

def _contributions(model, cols: list[str], row: pd.DataFrame) -> dict | None:
    if model is None:
        return None
    inner = model.named_steps["model"]
    imputer = model.named_steps["impute"]
    names = list(cols)
    if getattr(imputer, "indicator_", None) is not None:
        names += [f"missing:{cols[i]}" for i in imputer.indicator_.features_]
    if hasattr(inner, "coef_"):
        x = model.named_steps["scale"].transform(imputer.transform(row[cols]))[0]
        contrib = inner.coef_ * x
        items = sorted(zip(names, contrib), key=lambda kv: -abs(kv[1]))
        return {
            "kind": "linear",
            "note": "coefficient × standardised feature value for this forecast; they sum (with the intercept) to the prediction",
            "intercept": float(inner.intercept_),
            "alpha": float(inner.alpha_),
            "items": [{"feature": n, "value": float(v)} for n, v in items[:10]],
        }
    if hasattr(inner, "feature_importances_"):
        items = sorted(zip(names, inner.feature_importances_), key=lambda kv: -kv[1])
        return {
            "kind": "global_importance",
            "note": "impurity-based importance of each feature in the fitted trees (global, not specific to this forecast)",
            "items": [{"feature": n, "value": float(v)} for n, v in items[:10] if v > 0],
        }
    return None


def final_forecasts(data: pd.DataFrame, horizon: int, primary: str, bt: pd.DataFrame, seed: int) -> list[dict]:
    target = f"target_{horizon}"
    usable = data.dropna(subset=REQUIRED_MARKET + ["close"])
    if usable.empty:
        return []
    latest = usable.iloc[[-1]]
    train = usable.dropna(subset=[target])
    resid = bt[bt["model_name"] == primary].sort_values("date").tail(365)
    resid = (resid["y_true"] - resid["y_pred"]).to_numpy()
    out = []
    for cand in CANDIDATES:
        preds, model = _fit_predict(cand, train, latest, target, seed)
        pred = float(preds[0])
        rec = {
            "model_name": cand.name,
            "is_primary": cand.name == primary,
            "feature_date": latest.index[0].strftime("%Y-%m-%d"),
            "target_date": (latest.index[0] + timedelta(days=horizon)).strftime("%Y-%m-%d"),
            "reference_price": float(latest["close"].iloc[0]),
            "predicted_return": pred,
            "sentiment_available": bool(latest["sentiment_available"].iloc[0]),
            "contributions": _contributions(model, FEATURE_SETS[cand.feature_set], latest) if cand.feature_set else None,
            "lower": None, "upper": None, "interval_note": None,
        }
        if cand.name == primary and len(resid) >= 100:
            lo, hi = np.quantile(resid, [0.1, 0.9])
            rec["lower"], rec["upper"] = pred + float(lo), pred + float(hi)
            rec["interval_note"] = (
                f"Empirical 80% range from the primary model's last {len(resid)} out-of-sample errors "
                "(10th–90th percentile). Not a guarantee; error spread changes with volatility."
            )
        out.append(rec)
    return out


# ── Orchestration ──────────────────────────────────────────────────────────

def train_and_forecast(engine: str, symbols: list[str] | None = None) -> dict:
    if not _train_lock.acquire(blocking=False):
        raise RuntimeError("a training run is already in progress")
    try:
        return _run(engine, symbols or list(settings.assets))
    finally:
        _train_lock.release()


def _run(engine: str, symbols: list[str]) -> dict:
    seed = settings.random_seed
    config = {
        "code_version": CODE_VERSION, "engine": engine, "horizons": list(HORIZONS),
        "study_start": settings.study_start, "validation_end": settings.validation_end,
        "min_train_days": settings.min_train_days, "refit_every": settings.refit_every, "seed": seed,
        "market_features": MARKET_FEATURES, "sentiment_features": SENTIMENT_FEATURES,
        "candidates": [c.name for c in CANDIDATES], "data_mode": settings.data_mode,
    }
    created = utc_now()
    digest = hashlib.sha1(json.dumps(config, sort_keys=True).encode()).hexdigest()[:6]
    run_id = f"run-{created.replace('-', '').replace(':', '')}-{digest}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO model_runs(run_id, created_at, status, data_mode, engine, config_json) VALUES (?,?,?,?,?,?)",
            (run_id, created, "running", settings.data_mode, engine, json.dumps(config)),
        )
    run_summary: dict = {"run_id": run_id, "assets": {}}
    try:
        for symbol in symbols:
            ds = build_dataset(symbol, engine)
            if ds.empty:
                run_summary["assets"][symbol] = {"status": "skipped", "reason": "no price data"}
                continue
            data = ds[ds.index >= pd.Timestamp(settings.study_start)]
            if data["close"].notna().sum() < settings.min_train_days + 90:
                run_summary["assets"][symbol] = {"status": "skipped", "reason": f"only {int(data['close'].notna().sum())} days of prices in the study window"}
                continue
            asset_summary = {
                "status": "ok",
                "data_start": data.index.min().strftime("%Y-%m-%d"),
                "data_end": data.index.max().strftime("%Y-%m-%d"),
                "price_days": int(data["close"].notna().sum()),
                "sentiment_days": int(data["sent_mean"].notna().sum()),
                "sentiment_coverage": float(data["sent_mean"].notna().mean()),
                "price_sources": data["price_source"].dropna().value_counts().to_dict(),
                "granger": [],
                "horizons": {},
            }
            for lags in (1, 2, 3):
                for direction in ("sentiment_to_returns", "returns_to_sentiment"):
                    asset_summary["granger"].append(granger_hac(data, lags, direction))
            regime = volatility_regime(data["vol_30"])
            for reg in ("high_vol", "low_vol"):
                g = granger_hac(data, 2, "sentiment_to_returns", mask=regime == reg)
                g["regime"] = reg
                asset_summary["granger"].append(g)
            _store_features(run_id, symbol, data)
            for h in HORIZONS:
                bt = walk_forward(data, h, seed)
                if bt.empty:
                    asset_summary["horizons"][str(h)] = {"status": "skipped", "reason": "not enough labelled rows"}
                    continue
                summ = summarise(bt, h)
                fcs = final_forecasts(data, h, summ["selected_model"], bt, seed)
                _store_backtest(run_id, symbol, h, bt)
                _store_forecasts(run_id, symbol, h, fcs, created)
                with get_conn() as conn:
                    conn.execute(
                        """INSERT INTO model_evaluations(run_id, symbol, horizon, selected_model, data_start, data_end, metrics_json)
                           VALUES (?,?,?,?,?,?,?)""",
                        (run_id, symbol, h, summ["selected_model"], asset_summary["data_start"], asset_summary["data_end"], json.dumps(summ)),
                    )
                asset_summary["horizons"][str(h)] = {"selected_model": summ["selected_model"], "n_oos": int(bt["date"].nunique())}
            run_summary["assets"][symbol] = asset_summary
        with get_conn() as conn:
            conn.execute("UPDATE model_runs SET status='completed', summary_json=? WHERE run_id=?", (json.dumps(run_summary, default=str), run_id))
        return run_summary
    except Exception as exc:
        with get_conn() as conn:
            conn.execute("UPDATE model_runs SET status='failed', message=? WHERE run_id=?", (f"{type(exc).__name__}: {exc}"[:500], run_id))
        raise


def _store_features(run_id: str, symbol: str, data: pd.DataFrame) -> None:
    cols = MARKET_FEATURES + SENTIMENT_FEATURES
    rows = [
        (run_id, symbol, idx.strftime("%Y-%m-%d"), json.dumps({c: (None if pd.isna(v) else round(float(v), 8)) for c, v in r.items()}))
        for idx, r in data[cols].iterrows()
    ]
    with get_conn() as conn:
        conn.executemany("INSERT OR REPLACE INTO feature_snapshots(run_id, symbol, date, features_json) VALUES (?,?,?,?)", rows)


def _store_backtest(run_id: str, symbol: str, h: int, bt: pd.DataFrame) -> None:
    rows = [
        (run_id, symbol, h, r.model_name, r.date.strftime("%Y-%m-%d"), r.segment, r.regime if isinstance(r.regime, str) else None, r.y_true, r.y_pred)
        for r in bt.itertuples(index=False)
    ]
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO backtest_predictions(run_id, symbol, horizon, model_name, date, segment, regime, y_true, y_pred)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )


def _store_forecasts(run_id: str, symbol: str, h: int, fcs: list[dict], created: str) -> None:
    with get_conn() as conn:
        for f in fcs:
            conn.execute(
                """INSERT OR IGNORE INTO forecasts(run_id, symbol, horizon, model_name, is_primary, created_at, feature_date,
                       target_date, reference_price, predicted_return, lower_return, upper_return, interval_note,
                       contributions_json, sentiment_available)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, symbol, h, f["model_name"], int(f["is_primary"]), created, f["feature_date"], f["target_date"],
                    f["reference_price"], f["predicted_return"], f["lower"], f["upper"], f["interval_note"],
                    json.dumps(f["contributions"]) if f["contributions"] else None, int(f["sentiment_available"]),
                ),
            )


def update_realized_returns() -> int:
    """Fills realised returns for forecasts whose target day has closed.
    Historical predictions are never modified otherwise."""
    from app.services.market_data import price_series

    with get_conn() as conn:
        pending = conn.execute(
            "SELECT id, symbol, feature_date, target_date FROM forecasts WHERE realized_return IS NULL"
        ).fetchall()
    updated = 0
    cache: dict[str, pd.Series] = {}
    for f in pending:
        if f["symbol"] not in cache:
            cache[f["symbol"]] = price_series(f["symbol"])["close"]
        close = cache[f["symbol"]]
        try:
            p0 = close.loc[pd.Timestamp(f["feature_date"])]
            p1 = close.loc[pd.Timestamp(f["target_date"])]
        except KeyError:
            continue
        if pd.notna(p0) and pd.notna(p1):
            with get_conn() as conn:
                conn.execute("UPDATE forecasts SET realized_return=?, realized_at=? WHERE id=?", (float(p1 / p0 - 1), utc_now(), f["id"]))
            updated += 1
    return updated

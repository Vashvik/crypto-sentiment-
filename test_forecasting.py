from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd

from app.services import forecasting
from app.services.features import add_targets, market_features


def _dataset(n=700, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D", name="date")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.02, n))), index=idx)
    p = pd.DataFrame({"close": close, "volume_usd": rng.uniform(1e9, 2e9, n)}, index=idx)
    f = market_features(p)
    for c in forecasting.FEATURE_SETS["market_sentiment"]:
        if c not in f:
            f[c] = rng.normal(0, 1, n)
    f["close"] = close
    f["sentiment_available"] = True
    return add_targets(f, close)


def test_walk_forward_respects_embargo(monkeypatch):
    """Every out-of-sample prediction must come from a model whose training
    rows all satisfy t + h <= prediction date (target fully observed)."""
    data = _dataset()
    seen = []
    original = forecasting._fit_predict

    def spy(cand, train, test, target, seed):
        seen.append((train.index.max(), test.index.min(), int(target.split("_")[1])))
        return original(cand, train, test, target, seed)

    monkeypatch.setattr(forecasting, "_fit_predict", spy)
    monkeypatch.setattr(forecasting, "settings", replace(forecasting.settings, min_train_days=300))
    for h in (1, 3):
        bt = forecasting.walk_forward(data, h, seed=0)
        assert not bt.empty
    assert seen
    for train_max, test_min, h in seen:
        assert train_max + timedelta(days=h) <= test_min


def test_summary_selects_lowest_validation_rmse():
    data = _dataset()
    bt = forecasting.walk_forward(data, 1, seed=0)
    s = forecasting.summarise(bt, 1)
    val = {n: m["validation"]["rmse"] for n, m in s["models"].items() if "validation" in m}
    assert s["selected_model"] == min(val, key=val.get)
    assert "ridge_sentiment_vs_ridge_market" in s["ablation"]["validation"]


def test_realized_returns_fill_without_touching_predictions(temp_db):
    from app.db import get_conn
    from app.services.market_data import _finalise, store_prices

    df = pd.DataFrame({"date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"], "close": [100.0, 110.0, 99.0, 120.0]})
    store_prices("BTC", _finalise(df), "csv")
    with get_conn() as conn:
        for h, target in ((1, "2024-01-02"), (3, "2024-01-04")):
            conn.execute(
                """INSERT INTO forecasts(run_id, symbol, horizon, model_name, is_primary, created_at, feature_date, target_date,
                   reference_price, predicted_return, sentiment_available) VALUES ('r', 'BTC', ?, 'zero', 1, 'x', '2024-01-01', ?, 100, 0.0, 1)""",
                (h, target),
            )
        conn.execute(
            """INSERT INTO forecasts(run_id, symbol, horizon, model_name, is_primary, created_at, feature_date, target_date,
               reference_price, predicted_return, sentiment_available) VALUES ('r', 'BTC', 1, 'zero', 1, 'x', '2024-01-04', '2024-01-05', 120, 0.0, 1)"""
        )
    assert forecasting.update_realized_returns() == 2
    with get_conn() as conn:
        rows = {(r["horizon"], r["feature_date"]): (r["realized_return"], r["predicted_return"]) for r in conn.execute("SELECT * FROM forecasts")}
    assert np.isclose(rows[(1, "2024-01-01")][0], 0.10)
    assert np.isclose(rows[(3, "2024-01-01")][0], 0.20)
    assert rows[(1, "2024-01-04")][0] is None  # target day not closed yet
    assert all(v[1] == 0.0 for v in rows.values())

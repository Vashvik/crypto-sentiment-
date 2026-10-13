import numpy as np
import pandas as pd

from app.services.evaluation import diebold_mariano, forecast_metrics, volatility_regime


def test_forecast_metrics():
    y = np.array([0.01, -0.02, 0.03, -0.01] * 5)
    pred = np.array([0.005, -0.01, 0.01, 0.002] * 5)
    m = forecast_metrics(y, pred, benchmark=np.zeros_like(y))
    assert np.isclose(m["mae"], np.mean(np.abs(y - pred)))
    assert np.isclose(m["rmse"], np.sqrt(np.mean((y - pred) ** 2)))
    assert np.isclose(m["r2_oos_vs_mean"], m["r2_oos_vs_zero"])
    assert np.isclose(m["direction_acc"], 0.75)
    assert forecast_metrics(y, np.zeros_like(y))["direction_acc"] is None  # undefined for a zero forecast


def test_diebold_mariano_sign_and_symmetry():
    rng = np.random.default_rng(1)
    y = rng.normal(0, 1, 400)
    good = y - rng.normal(0, 0.3, 400)
    bad = y - rng.normal(0, 1.0, 400)
    r = diebold_mariano(y - good, y - bad, horizon=1)
    assert r["stat"] < 0 and r["p_value"] < 0.01
    r2 = diebold_mariano(y - bad, y - good, horizon=1)
    assert np.isclose(r["stat"], -r2["stat"])


def test_regime_uses_only_past_information():
    rng = np.random.default_rng(2)
    vol = pd.Series(rng.uniform(0.01, 0.05, 300), index=pd.date_range("2024-01-01", periods=300))
    base = volatility_regime(vol)
    vol2 = vol.copy(); vol2.iloc[200:] = 0.5
    changed = volatility_regime(vol2)
    pd.testing.assert_series_equal(base.iloc[:200], changed.iloc[:200])


def test_granger_mask_keeps_calendar_lags():
    from app.services.evaluation import granger_hac

    rng = np.random.default_rng(5)
    n = 600
    idx = pd.date_range("2022-01-01", periods=n)
    s = pd.Series(rng.normal(0, 1, n), index=idx)
    r = 0.5 * s.shift(1).fillna(0) + rng.normal(0, 0.5, n)  # sentiment truly leads returns by one day
    frame = pd.DataFrame({"ret_1": r, "sent_mean": s, "vol_7": 1.0}, index=idx)
    every_other = pd.Series(np.arange(n) % 2 == 0, index=idx)
    res = granger_hac(frame, 1, "sentiment_to_returns", mask=every_other)
    assert res["p_value"] < 0.001  # lag structure survives masking
    assert res["n"] <= n // 2

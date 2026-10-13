"""Forecast evaluation: error metrics, the Diebold–Mariano test used for the
market-only vs market+sentiment ablation, volatility regimes and HAC-robust
Granger-causality tests."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats


def forecast_metrics(y: np.ndarray, pred: np.ndarray, benchmark: np.ndarray | None = None) -> dict:
    """MAE, RMSE, out-of-sample R² and directional accuracy.

    r2_oos_vs_mean  = 1 − SSE(model) / SSE(historical-mean forecast)
                      (Campbell & Thompson 2008 style; > 0 means the model beat
                      the mean forecast that was available at the time)
    r2_oos_vs_zero  = 1 − SSE(model) / Σ y²
    direction_acc   = share of days where sign(pred) = sign(actual), over days
                      with a non-zero forecast and non-zero outcome. Undefined
                      for a forecast that is always exactly zero.
    """
    y = np.asarray(y, float)
    pred = np.asarray(pred, float)
    err = y - pred
    sse = float(np.sum(err**2))
    out = {
        "n": int(len(y)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(math.sqrt(np.mean(err**2))),
        "r2_oos_vs_zero": float(1 - sse / np.sum(y**2)) if np.sum(y**2) > 0 else None,
    }
    if benchmark is not None:
        bench_sse = float(np.sum((y - np.asarray(benchmark, float)) ** 2))
        out["r2_oos_vs_mean"] = float(1 - sse / bench_sse) if bench_sse > 0 else None
    mask = (pred != 0) & (y != 0)
    out["direction_acc"] = float(np.mean(np.sign(pred[mask]) == np.sign(y[mask]))) if mask.sum() >= 10 else None
    out["up_share"] = float(np.mean(y > 0)) if len(y) else None
    return out


def newey_west_variance(x: np.ndarray, lags: int) -> float:
    x = np.asarray(x, float) - np.mean(x)
    n = len(x)
    gamma0 = np.dot(x, x) / n
    var = gamma0
    for k in range(1, lags + 1):
        w = 1 - k / (lags + 1)
        var += 2 * w * np.dot(x[k:], x[:-k]) / n
    return float(var)


def diebold_mariano(e_a: np.ndarray, e_b: np.ndarray, horizon: int) -> dict:
    """Tests equal squared-error accuracy of forecasts A and B.
    d_t = e_A² − e_B²; negative mean_d means A is more accurate.
    HAC variance with h−1 lags (overlapping h-step targets) and the
    Harvey–Leybourne–Newbold small-sample correction, two-sided p-value."""
    d = np.asarray(e_a, float) ** 2 - np.asarray(e_b, float) ** 2
    n = len(d)
    if n < 30:
        return {"n": n, "stat": None, "p_value": None, "note": "too few observations"}
    var = newey_west_variance(d, max(horizon - 1, 0))
    if var <= 0:
        return {"n": n, "stat": None, "p_value": None, "note": "zero variance"}
    dm = d.mean() / math.sqrt(var / n)
    h = horizon
    correction = math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    stat = dm * correction
    p = 2 * stats.t.sf(abs(stat), df=n - 1)
    return {"n": n, "mean_loss_diff": float(d.mean()), "stat": float(stat), "p_value": float(p)}


def volatility_regime(vol_30: pd.Series) -> pd.Series:
    """'high_vol' when 30-day volatility on day t exceeds the median of all
    earlier days' 30-day volatility (expanding, shifted by one day), otherwise
    'low_vol'. Uses only information available at t."""
    past_median = vol_30.expanding(min_periods=60).median().shift(1)
    regime = pd.Series(np.where(vol_30 > past_median, "high_vol", "low_vol"), index=vol_30.index)
    return regime.where(past_median.notna() & vol_30.notna())


def granger_hac(frame: pd.DataFrame, lags: int, direction: str, maxlags_hac: int = 5, mask: pd.Series | None = None) -> dict:
    """HAC-robust Granger test.

    sentiment_to_returns: r(t+1) ~ c + Σ r(t−i) + vol_7(t) + Σ S(t−i), H0: all S coefs = 0
    returns_to_sentiment: S(t+1) ~ c + Σ S(t−i) + vol_7(t) + Σ r(t−i), H0: all r coefs = 0
    with i = 0…lags−1. Tests incremental predictive information only; it
    does not establish economic causation.

    `mask` restricts the regression to some days (e.g. one volatility regime).
    Lags are always built on the full daily series first, so a lag is the
    previous calendar day even when that day is outside the mask.
    """
    import statsmodels.api as sm

    r = frame["ret_1"]
    s = frame["sent_mean"]
    data = pd.DataFrame(index=frame.index)
    if direction == "sentiment_to_returns":
        data["y"] = r.shift(-1)
        own, other = r, s
    else:
        data["y"] = s.shift(-1)
        own, other = s, r
    for i in range(lags):
        data[f"own_{i}"] = own.shift(i)
    data["vol_7"] = frame["vol_7"]
    test_cols = []
    for i in range(lags):
        data[f"x_{i}"] = other.shift(i)
        test_cols.append(f"x_{i}")
    if mask is not None:
        data = data[mask.reindex(data.index).fillna(False).astype(bool)]
    data = data.dropna()
    if len(data) < 100:
        return {"lags": lags, "direction": direction, "n": int(len(data)), "note": "too few complete rows"}
    X = sm.add_constant(data.drop(columns="y"))
    res = sm.OLS(data["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags_hac})
    R = np.zeros((len(test_cols), X.shape[1]))
    for row, col in enumerate(test_cols):
        R[row, list(X.columns).index(col)] = 1
    wald = res.wald_test(R, use_f=True, scalar=True)
    return {
        "lags": lags,
        "direction": direction,
        "n": int(len(data)),
        "f_stat": float(wald.statistic),
        "p_value": float(wald.pvalue),
        "coefficients": {c: float(res.params[c]) for c in test_cols},
        "r2": float(res.rsquared),
    }

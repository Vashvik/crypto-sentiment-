"""Feature engineering and forecast targets.

Timing convention (the whole leakage argument rests on it):
- Row t is the close of UTC day t. Every feature in row t uses only prices
  up to and including the close of t and texts published before the end of t.
- Target for horizon h: R(t, h) = P(t+h) / P(t) − 1 (simple return).
- The series sits on a complete calendar index; missing prices stay NaN, so
  a shift of k rows is exactly k days and a gap can never become a fake return.
- Rows whose forward window is incomplete (t+h not yet observed or missing)
  have a NaN target and are excluded from training and evaluation.
- Imputation and scaling are NOT done here; they are fitted inside the model
  pipeline on training rows only (see forecasting.py).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import HORIZONS
from app.services.aggregation import daily_sentiment
from app.services.market_data import price_series

MARKET_FEATURES = [
    "ret_1",       # log return over day t
    "ret_lag1",    # log return over day t-1
    "ret_lag2",    # log return over day t-2
    "mom_5",       # 5-day momentum (sum of log returns)
    "mom_20",      # 20-day momentum
    "vol_7",       # 7-day realised volatility (std of daily log returns)
    "vol_30",      # 30-day realised volatility
    "vol_ratio",   # vol_7 / vol_30
    "volume_chg",  # log(volume_t / mean volume over t-7..t-1)
    "ma_gap_20",   # close / 20-day moving average − 1
]

SENTIMENT_FEATURES = [
    "sent_mean",    # aggregated sentiment S(t)
    "sent_lag1",    # S(t-1)
    "sent_ma3",     # mean of S over t-2..t (available days)
    "sent_ma7",     # mean of S over t-6..t
    "sent_shock",   # S(t) − mean S over t-29..t
    "pos_prop",     # share of positive texts on day t
    "neg_prop",     # share of negative texts on day t
    "log_count",    # log(1 + number of texts on day t)
    "count_shock",  # log_count − mean log_count over t-30..t-1 (attention spike)
]

FEATURE_SETS = {
    "market": MARKET_FEATURES,
    "market_sentiment": MARKET_FEATURES + SENTIMENT_FEATURES,
}


def market_features(prices: pd.DataFrame) -> pd.DataFrame:
    close = prices["close"].astype(float)
    logret = np.log(close).diff()
    f = pd.DataFrame(index=prices.index)
    f["ret_1"] = logret
    f["ret_lag1"] = logret.shift(1)
    f["ret_lag2"] = logret.shift(2)
    f["mom_5"] = logret.rolling(5, min_periods=5).sum()
    f["mom_20"] = logret.rolling(20, min_periods=15).sum()
    f["vol_7"] = logret.rolling(7, min_periods=6).std()
    f["vol_30"] = logret.rolling(30, min_periods=25).std()
    f["vol_ratio"] = f["vol_7"] / f["vol_30"]
    volume = prices["volume_usd"].astype(float).where(lambda v: v > 0)
    f["volume_chg"] = np.log(volume / volume.shift(1).rolling(7, min_periods=5).mean())
    ma20 = close.rolling(20, min_periods=15).mean()
    f["ma_gap_20"] = close / ma20 - 1
    return f.replace([np.inf, -np.inf], np.nan)


def sentiment_features(daily: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    f = pd.DataFrame(index=index)
    if daily.empty:
        for col in SENTIMENT_FEATURES + ["n_records", "n_news", "n_social", "sent_std", "neu_prop", "sent_news", "sent_social"]:
            f[col] = np.nan
        return f
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date").reindex(index)
    sent = d["sent_mean"].astype(float)
    count = d["n_records"].astype(float)  # NaN outside the text-coverage window, 0 for empty days
    f["sent_mean"] = sent
    f["sent_lag1"] = sent.shift(1)
    f["sent_ma3"] = sent.rolling(3, min_periods=1).mean()
    f["sent_ma7"] = sent.rolling(7, min_periods=1).mean()
    f["sent_shock"] = sent - sent.rolling(30, min_periods=5).mean()
    f["pos_prop"] = d["pos_prop"].astype(float)
    f["neg_prop"] = d["neg_prop"].astype(float)
    log_count = np.log1p(count)
    f["log_count"] = log_count
    f["count_shock"] = log_count - log_count.shift(1).rolling(30, min_periods=10).mean()
    # Descriptive columns for the dashboard (not model inputs)
    for col in ("n_records", "n_news", "n_social", "sent_std", "neu_prop", "sent_news", "sent_social"):
        f[col] = d[col].astype(float)
    return f


def add_targets(frame: pd.DataFrame, close: pd.Series, horizons=HORIZONS) -> pd.DataFrame:
    for h in horizons:
        frame[f"target_{h}"] = close.shift(-h) / close - 1
    return frame


def build_dataset(symbol: str, engine: str) -> pd.DataFrame:
    prices = price_series(symbol)
    if prices.empty:
        return pd.DataFrame()
    frame = market_features(prices)
    frame = frame.join(sentiment_features(daily_sentiment(symbol, engine), prices.index))
    frame["close"] = prices["close"].astype(float)
    frame["volume_usd"] = prices["volume_usd"].astype(float)
    frame["price_source"] = prices["source"]
    frame = add_targets(frame, frame["close"])
    frame["sentiment_available"] = frame["sent_mean"].notna()
    return frame

import numpy as np
import pandas as pd

from app.services.features import add_targets, market_features, sentiment_features


def _prices(n=80, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", name="date")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame({"close": close, "volume_usd": rng.uniform(1e9, 2e9, n)}, index=idx)


def test_forward_return_definition():
    p = _prices()
    t = add_targets(pd.DataFrame(index=p.index), p["close"], horizons=(1, 3))
    i = 10
    assert np.isclose(t["target_1"].iloc[i], p["close"].iloc[i + 1] / p["close"].iloc[i] - 1)
    assert np.isclose(t["target_3"].iloc[i], p["close"].iloc[i + 3] / p["close"].iloc[i] - 1)
    assert t["target_3"].iloc[-3:].isna().all()  # incomplete forward windows


def test_missing_price_day_never_creates_a_fake_return():
    p = _prices()
    p.iloc[40, p.columns.get_loc("close")] = np.nan
    f = market_features(p)
    t = add_targets(pd.DataFrame(index=p.index), p["close"], horizons=(1, 3))
    assert pd.isna(f["ret_1"].iloc[40]) and pd.isna(f["ret_1"].iloc[41])
    assert pd.isna(t["target_1"].iloc[39]) and pd.isna(t["target_3"].iloc[37])


def test_features_do_not_change_when_future_data_changes():
    """Leakage guard: altering prices and sentiment after day t must leave
    every feature at or before t untouched."""
    p = _prices()
    sent = pd.DataFrame({"date": p.index.strftime("%Y-%m-%d"), "sent_mean": np.linspace(-0.5, 0.5, len(p)),
                         "n_records": 5, "pos_prop": 0.5, "neg_prop": 0.2, "n_news": 5, "n_social": 0,
                         "sent_std": 0.1, "neu_prop": 0.3, "sent_news": 0.1, "sent_social": np.nan})
    base = market_features(p).join(sentiment_features(sent, p.index))
    t = 50
    p2 = p.copy(); p2.iloc[t + 1:, 0] *= 3; p2.iloc[t + 1:, 1] *= 0.1
    s2 = sent.copy(); s2.loc[t + 1:, "sent_mean"] = 0.99; s2.loc[t + 1:, "n_records"] = 500
    changed = market_features(p2).join(sentiment_features(s2, p.index))
    pd.testing.assert_frame_equal(base.iloc[: t + 1], changed.iloc[: t + 1])


def test_days_without_text_coverage_are_nan_not_zero():
    p = _prices(20)
    sent = pd.DataFrame({"date": p.index[5:10].strftime("%Y-%m-%d"), "sent_mean": 0.1, "n_records": [3, 0, 2, 1, 4],
                         "pos_prop": 0.5, "neg_prop": 0.1, "n_news": 3, "n_social": 0, "sent_std": 0.1,
                         "neu_prop": 0.4, "sent_news": 0.1, "sent_social": np.nan})
    sent.loc[1, "sent_mean"] = np.nan  # the zero-count day
    f = sentiment_features(sent, p.index)
    assert pd.isna(f["log_count"].iloc[0])        # before coverage: unknown
    assert f["log_count"].iloc[6] == 0.0          # covered day with zero texts
    assert pd.isna(f["sent_mean"].iloc[6])        # …and no sentiment value

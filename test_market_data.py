from datetime import datetime, timedelta, timezone

import pandas as pd

from app.services.market_data import _finalise, normalise_binance, normalise_coingecko


def _ms(dt):
    return int(dt.timestamp() * 1000)


def test_coingecko_midnight_point_is_previous_day_close_and_partial_dropped():
    d0 = datetime(2025, 1, 2, tzinfo=timezone.utc)
    data = {
        "prices": [[_ms(d0), 100.0], [_ms(d0 + timedelta(days=1)), 110.0], [_ms(d0 + timedelta(days=1, hours=7)), 999.0]],
        "total_volumes": [[_ms(d0), 5.0], [_ms(d0 + timedelta(days=1)), 6.0], [_ms(d0 + timedelta(days=1, hours=7)), 7.0]],
        "market_caps": [[_ms(d0), 1.0], [_ms(d0 + timedelta(days=1)), 2.0], [_ms(d0 + timedelta(days=1, hours=7)), 3.0]],
    }
    df = normalise_coingecko(data)
    assert list(df["date"]) == ["2025-01-01", "2025-01-02"]
    assert list(df["close"]) == [100.0, 110.0]
    assert 999.0 not in df["close"].values


def test_binance_drops_open_candle_and_keeps_ohlc():
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    closed_open = now - timedelta(days=2)
    rows = [
        [_ms(closed_open), "1", "2", "0.5", "1.5", "10", _ms(closed_open + timedelta(days=1)) - 1, "15"],
        [_ms(now), "1.5", "1.6", "1.4", "1.55", "3", _ms(now + timedelta(days=1)) - 1, "4"],
    ]
    df = normalise_binance(rows)
    assert len(df) == 1
    r = df.iloc[0]
    assert r["date"] == closed_open.strftime("%Y-%m-%d")
    assert (r["open"], r["high"], r["low"], r["close"], r["volume_usd"]) == (1.0, 2.0, 0.5, 1.5, 15.0)


def test_finalise_removes_bad_rows_duplicates_and_today():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    df = pd.DataFrame({"date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03", today],
                       "close": [1.0, 2.0, -5.0, float("nan"), 3.0]})
    out = _finalise(df)
    assert list(out["date"]) == ["2024-01-01"]
    assert out["close"].iloc[0] == 2.0  # last duplicate wins

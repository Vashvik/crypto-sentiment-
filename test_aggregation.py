import math

import pandas as pd

from app.services.aggregation import _fill_missing_days, aggregate_frame


def test_equal_weight_mean_and_proportions():
    df = pd.DataFrame({
        "symbol": ["BTC"] * 4,
        "date": ["2024-01-01"] * 3 + ["2024-01-03"],
        "source_type": ["news", "news", "social", "news"],
        "score": [0.5, -0.5, 0.3, 0.2],
        "label": ["positive", "negative", "positive", "positive"],
    })
    out = aggregate_frame(df).set_index("date")
    d1 = out.loc["2024-01-01"]
    assert d1["n_records"] == 3 and d1["n_news"] == 2 and d1["n_social"] == 1
    assert math.isclose(d1["sent_mean"], 0.1)
    assert math.isclose(d1["pos_prop"], 2 / 3) and math.isclose(d1["neg_prop"], 1 / 3) and d1["neu_prop"] == 0
    assert math.isclose(d1["sent_news"], 0.0) and math.isclose(d1["sent_social"], 0.3)


def test_missing_day_is_missing_not_neutral():
    df = pd.DataFrame({
        "symbol": ["BTC", "BTC"], "date": ["2024-01-01", "2024-01-03"], "source_type": ["news", "news"],
        "score": [0.4, -0.2], "label": ["positive", "negative"],
    })
    filled = _fill_missing_days(aggregate_frame(df), df, None).set_index("date")
    gap = filled.loc["2024-01-02"]
    assert gap["n_records"] == 0
    assert pd.isna(gap["sent_mean"])  # not 0.0

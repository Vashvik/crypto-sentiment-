import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(temp_db):
    from app.services.market_data import _finalise, store_prices

    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    df = pd.DataFrame({"date": idx.strftime("%Y-%m-%d"), "close": np.linspace(100, 130, 30), "volume_usd": 1e9})
    store_prices("BTC", _finalise(df), "csv")
    import main

    with TestClient(main.app) as c:
        yield c


def test_health_and_assets(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assets = {a["symbol"]: a for a in client.get("/api/v1/assets").json()["assets"]}
    assert assets["BTC"]["has_data"] and assets["BTC"]["last_close"] == 130
    assert np.isclose(assets["BTC"]["change_1d"], 130 / (130 - 30 / 29) - 1)
    assert assets["ETH"]["has_data"] is False


def test_market_range_and_validation(client):
    r = client.get("/api/v1/market/BTC", params={"start": "2024-01-10", "end": "2024-01-12"})
    rows = r.json()["rows"]
    assert [x["date"] for x in rows] == ["2024-01-10", "2024-01-11", "2024-01-12"]
    assert rows[0]["return_1d"] is not None  # computed before slicing
    assert client.get("/api/v1/market/DOGE").status_code == 404
    assert client.get("/api/v1/market/BTC", params={"start": "2024-02-30"}).status_code == 422
    assert client.get("/api/v1/market/BTC", params={"start": "2024-03-01", "end": "2024-01-01"}).status_code == 422
    assert client.get("/api/v1/market/ETH").status_code == 404  # no data stored


def test_empty_states_and_jobs(client):
    assert client.get("/api/v1/forecasts/BTC/latest").status_code == 404
    assert client.get("/api/v1/backtest/BTC", params={"horizon": 2}).status_code == 422
    assert client.post("/api/v1/jobs/refresh").status_code == 409  # sample mode
    r = client.post("/api/v1/sentiment/analyze", json={"text": "Bitcoin rallies, great news for investors", "engine": "vader"})
    assert r.status_code == 200 and r.json()["score"] > 0 and r.json()["assets"] == ["BTC"]
    assert client.post("/api/v1/sentiment/analyze", json={"text": "x"}).status_code == 422

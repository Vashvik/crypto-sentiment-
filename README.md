# CryptoSentinel

**Aggregated Daily Sentiment Analysis for Predicting Short-Term Crypto Returns**

A research dashboard that asks one question:

> Does aggregated daily sentiment from news headlines and social media help predict cryptocurrency returns over the next 1–3 days **after accounting for volatility and momentum**, and is its predictive value stable across market regimes?

It ingests prices and crypto news/social text, scores every text for sentiment, aggregates the scores per asset and UTC day, trains forecasting models with and without sentiment, evaluates them out-of-sample with walk-forward validation, and shows everything on a web dashboard.

> **Academic project, not a trading system.** The forecasts ignore transaction costs, slippage, liquidity and risk management, and they come with large errors. On the bundled data, no model beat a naive baseline (see *Results*). Nothing here is investment advice.

---

## 1. Main features

| Area | What it does |
| --- | --- |
| Market data | Daily close, volume and market cap (bundled Coin Metrics history for BTC/ETH); live CoinGecko or Binance OHLCV in live mode. UTC days, gaps kept as gaps. |
| Text ingestion | Bundled CryptoPanic dataset (42k BTC/ETH headlines and posts, 2020 to 2 Dec 2025); live RSS feeds; optional CryptoPanic API and Reddit (OAuth). Cleaning, de-duplication, bot-template filter, language filter, asset tagging. |
| Sentiment | VADER, VADER + crypto lexicon, a TF-IDF classifier trained on CryptoPanic community votes, optional FinBERT. The engine is chosen on held-out validation data. |
| Aggregation | Equal-weight daily index per asset plus counts, positive/neutral/negative shares, dispersion, news vs social means. Missing days stay missing. |
| Forecasting | 1-day and 3-day returns; zero and historical-mean baselines, Ridge and gradient boosting, each with market-only and market + sentiment features. |
| Evaluation | Expanding-window walk-forward with an h-day embargo; validation period for model selection, untouched test period; MAE, RMSE, R²<sub>OOS</sub>, direction accuracy; Diebold–Mariano ablation; volatility regimes; HAC Granger tests in both directions. |
| Dashboard | Overview cards, market overview, sentiment dashboard with drill-down to individual headlines, prediction dashboard, methodology/results page, data and model status page with job controls. |

## 2. Technology stack

Kept from the original Bullseye codebase:

- **Frontend:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, `lightweight-charts` 5, SWR. The original design-system primitives (`components/ui`), theme system (light/dark, set before first paint), server-side `/api/backend` proxy and backend warm-up indicator are kept.
- **Backend:** Python FastAPI with `slowapi` rate limits and CORS (as before).

New or changed:

- **Storage:** SQLite (one file, created automatically). This replaces Supabase, so no account or server is needed.
- **Analysis:** pandas, NumPy, scikit-learn, statsmodels, SciPy, vaderSentiment, httpx, feedparser.
- Fonts are bundled from npm (`@fontsource-variable`), so builds don't need Google Fonts.

## 3. Architecture and data flow

```
           ┌──────────── backend (FastAPI, python) ─────────────────────────────┐
 Coin Metrics CSV ─┐                                                            │
 CoinGecko/Binance ┴─► market_data ──► market_prices ─┐                         │
                                                      ├─► features ─► forecasting ─► model_runs
 CryptoPanic CSV ──┐                                  │      │            │          model_evaluations
 RSS / CP API /    ┴─► news_ingestion ─► text_records │      │            ├────────► backtest_predictions
 Reddit                 (clean, dedupe,   text_assets │      │            └────────► forecasts (append-only)
                         tag assets)          │       │      └─► feature_snapshots
                                              ▼       │
                                     sentiment ─► sentiment_scores
                                              │       │
                                              ▼       │
                                     aggregation ─► daily_sentiment ─┘
           └──────────── main.py: /api/v1/* (read-only, plus background jobs) ──────┘
                                              ▲
 Browser ─► Next.js (frontend) ─► /api/backend/* proxy ─┘
```

The dashboard only **reads** stored results. Slow steps (live fetching, training) run as a background job behind a lock, so a page refresh never retrains anything.

## 4. Directory structure

```
backend/
  main.py                      FastAPI app: routes, validation, rate limits, CORS
  app/config.py                settings from environment, asset registry
  app/db.py                    SQLite schema + migrations, ingestion log
  app/services/
    http.py                    timeouts, retries, 429 back-off, response cache
    market_data.py             providers (sample CSV, CoinGecko, Binance, CSV import), price series
    text_processing.py         cleaning, hashes, language/spam filters, asset tagging
    news_ingestion.py          sources (sample, CSV, RSS, CryptoPanic API, Reddit), de-duplication, bot filter
    sentiment.py               engines, vote-trained classifier, engine evaluation, scoring
    aggregation.py             daily sentiment index
    features.py                market + sentiment features, forward-return targets
    evaluation.py              metrics, Diebold–Mariano, regimes, HAC Granger
    forecasting.py             candidates, walk-forward, selection, forecasts, realised returns
    pipeline.py                end-to-end orchestration with a run lock
  scripts/pipeline.py          command-line entry point
  data/sample/                 bundled historical data (see "Data sources")
  tests/                       pytest unit and API tests
frontend/
  app/                         routes: / (dashboard), /methodology, /status, /privacy, /terms, api/backend proxy
  components/dashboard/        overview, market, sentiment and prediction sections
  components/research/         methodology/results page and status page
  components/charts/           lightweight-charts wrapper and small SVG charts
  components/ui/               design-system primitives (kept from the original)
  lib/api.ts                   typed API client (SWR)
```

## 5. Installation

Requirements: **Python 3.11+** (tested on 3.13) and **Node.js 20.9+** (tested on 22).

### Backend

macOS / Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optional: defaults work as they are
```

Windows (PowerShell):

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### Frontend

```bash
cd frontend
npm ci              # or: npm install
```

## 6. API keys

**None are required.** The bundled sample works offline, and live mode works with free endpoints that need no key (CoinGecko public API, Binance public market data, RSS feeds).

Optional keys go in `backend/.env` only, never in the frontend:

| Variable | Gives you |
| --- | --- |
| `COINGECKO_API_KEY` | Higher CoinGecko rate limits (free "Demo" key). |
| `CRYPTOPANIC_API_KEY` | Live tagged headlines from the CryptoPanic developer API. Add `cryptopanic_api` to `NEWS_SOURCES`. |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Reddit posts through app-only OAuth (Reddit requires OAuth for API access). Add `reddit` to `NEWS_SOURCES`. |
| `JOB_TOKEN` | If set, starting jobs needs header `X-Job-Token`. Use it on a public deployment. |

## 7. Run the pipeline (initialise, load, score, aggregate, train, evaluate, forecast)

From `backend/` with the virtual environment active:

```bash
python scripts/pipeline.py all
```

This single command creates the database, loads the sample data, trains the vote-based text classifier, evaluates the sentiment engines and picks one, scores every text, builds the daily index, runs the walk-forward evaluation for every asset and horizon, and stores the forecasts. It takes about 3 minutes on a laptop. It is idempotent: re-running it doesn't duplicate data.

Other commands:

```bash
python scripts/pipeline.py init-db                 # create/migrate the database only
python scripts/pipeline.py load-sample             # load bundled data only
python scripts/pipeline.py score                   # (re)train text model, evaluate engines, score, aggregate
python scripts/pipeline.py train                   # score + aggregate + train + forecast
python scripts/pipeline.py train --engine vader    # force a sentiment engine
python scripts/pipeline.py refresh-live            # fetch live prices + news, score, aggregate
python scripts/pipeline.py all --live              # everything, including live fetching
python scripts/pipeline.py import-text my.csv      # your own texts: published_at,title[,body,source,url,symbols]
python scripts/pipeline.py import-prices my.csv    # your own prices: date,symbol,close[,open,high,low,volume_usd,market_cap_usd]
python scripts/pipeline.py status
```

Database migrations are applied automatically on start (`schema_version` table in `app/db.py`).

## 8. Run the app

Terminal 1, backend:

```bash
cd backend
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
uvicorn main:app --port 8000
```

Terminal 2, frontend:

```bash
cd frontend
npm run dev                      # development, or: npm run build && npm start
```

Open **http://localhost:3000**. Interactive API docs are at http://localhost:8000/docs.

### Live mode

Set `DATA_MODE=live` in `backend/.env` and restart the backend. Then either run `python scripts/pipeline.py refresh-live` (and `train` to refit), or use the buttons on the **Data & model status** page. A daily scheduled task (cron or Windows Task Scheduler) running `refresh-live` builds up live text history over time. RSS feeds only return their latest items, so live sentiment history starts on the day you begin collecting.

## 9. Data sources and licences

| Data | Source | Licence / terms |
| --- | --- | --- |
| BTC, ETH daily price, volume, market cap 2020 – 2 Dec 2025 (`data/sample/prices_daily_coinmetrics.csv`) | [Coin Metrics Community Data](https://github.com/coinmetrics/data) (`PriceUSD`, `volume_reported_spot_usd_1d`, `CapMrktCurUSD`) | CC BY-NC 4.0: non-commercial use with attribution |
| 42,474 BTC/ETH-tagged headlines and posts (`data/sample/news_cryptopanic_btc_eth.csv.gz`) | [CryptoPanic news dataset](https://github.com/soheilrahsaz/cryptoNewsDataset) by Soheil Rahsaz | CC0 |
| Live prices | CoinGecko public API, Binance public market data (`data-api.binance.vision`) | Provider terms; free tiers rate-limited; CoinGecko attribution shown |
| Live text | Publisher RSS feeds; CryptoPanic API; Reddit API | Provider terms |

The sample has no daily open/high/low (Coin Metrics publishes a daily reference rate). Live Binance data adds OHLC. SOL has no bundled price history, so it is skipped until live mode fetches it.

## 10. Methodology summary

**Daily convention.** All timestamps are UTC. Day *d* is 00:00–24:00 UTC; the close of *d* is the price at the end of that window. CoinGecko's 00:00 point is mapped to the previous day's close and Binance candles to their opening day. The running day is never stored. Missing price days stay `NaN` on a full calendar index, so a gap never becomes a fake return.

**Text cleaning.** HTML/URL removal and Unicode normalisation; exact duplicates (normalised headline) kept once; texts under 4 words, non-English text and obvious promotions are excluded but kept on record. Bot templates (posts identical except for numbers) are excluded after their third appearance, counting only earlier posts. Asset links come from the source's coin tags, otherwise whole-word keywords.

**Sentiment engines and selection.** CryptoPanic readers vote on headlines. A headline is labelled positive if it has at least 2 positive votes and twice as many positive as negative votes, and negative the other way round. The vote-trained TF-IDF + logistic regression model is trained only on headlines up to 31 Dec 2021, before the study window. All engines are scored on labelled headlines from the validation period (2022-01-01 to 2024-06-30), and `auto` picks the highest ROC-AUC. On the bundled data that is **VADER + crypto lexicon** (validation AUC 0.698, vs 0.680 for the vote classifier and 0.664 for plain VADER). Test-period agreement is reported, not used.

**Daily index.** `S(a, d) = Σ wᵢ sᵢ / Σ wᵢ` with equal weights, plus counts, shares, standard deviation, and news/social means. A day with no text has `S = NULL` and count 0. It is never treated as neutral.

**Targets.** `R(t, h) = P(t+h) / P(t) − 1` for h = 1 and 3. Rows with incomplete windows are dropped.

**Features.** Market (10): today's and two lagged log returns, 5- and 20-day momentum, 7- and 30-day volatility and their ratio, volume vs its 7-day mean, gap to the 20-day average. Sentiment (9): S(t), S(t−1), 3- and 7-day means, S minus its 30-day mean, positive and negative shares, log text count and its spike vs the 30-day mean. All use data up to the close of *t*. Imputation (training medians + missing flags) and scaling happen inside each model pipeline, fitted on that refit's training rows only.

**Walk-forward.** The study window starts 2022-01-01, and the first 365 days are training-only. The window expands with a refit every 30 days. For a block starting at day *s*, training rows satisfy *t + h ≤ s*; this embargo stops overlapping 3-day targets leaking. Predictions up to 2024-06-30 form the **validation** period and select the primary model (lowest RMSE, baselines included). Later predictions form the **test** period.

**Ablation.** Each model runs with market features and with market + sentiment features. Diebold–Mariano tests on squared errors use Newey–West variance and the Harvey–Leybourne–Newbold correction. They are run per period and per volatility regime. A day is *high volatility* if its 30-day volatility exceeds the median of all earlier days.

**Granger.** OLS of r(t+1) on own lags, 7-day volatility and sentiment lags (and the reverse: sentiment on its own lags and return lags), with HAC standard errors and a Wald test. Lags are 1, 2 and 3; there are also regime-restricted tests. These show incremental predictive information, not causation.

**Uncertainty.** The primary forecast's 80% range is the 10th–90th percentile of its last 365 out-of-sample errors. It is empirical, not a guarantee, and labelled as such.

## 11. Results on the bundled data (reference run, 13 Oct 2026)

The run uses BTC and ETH from 2022-01-01 to 2025-12-02. There are about 1,066 out-of-sample days per asset and horizon (validation Jan 2023 – Jun 2024, test Jul 2024 – Nov 2025), and sentiment is present on 98–99% of days.

- **No model beat the zero-return baseline** on validation RMSE for either asset or horizon, so the dashboard's primary forecast is "no change", together with its empirical error range. The other models' forecasts are shown next to it.
- **Adding sentiment did not significantly change accuracy.** All 16 Diebold–Mariano comparisons (2 assets × 2 horizons × Ridge/boosting × validation/test) have p > 0.05. The closest are BTC 3-day Ridge on validation (p ≈ 0.07, sentiment *worse*) and ETH 3-day Ridge on test (p ≈ 0.08, sentiment *better*). Splitting by volatility regime doesn't change this.
- **Granger:** sentiment does not predict next-day returns (BTC p = 0.50, ETH p = 0.48 at lag 1), but past returns strongly predict next-day sentiment (F = 47 for BTC and 34 for ETH, p < 0.001). Mood follows the market more than it leads it.

These conclusions are produced fresh by every run and appear on the Methodology page, generated from the stored numbers. If you change the data, dates or engine, the page updates with them.

## 12. API endpoints

All under `/api/v1`. Errors are `{"detail": "..."}` with 404 for unknown assets or missing data, 422 for invalid input, 409 for a busy or disabled job, and 429 for rate limits.

| Method & path | Purpose |
| --- | --- |
| `GET /health` | Liveness |
| `GET /status` | Data mode, coverage, source health, engine, latest run, job state |
| `GET /assets` | Supported assets with latest close, 1-day change, coverage |
| `GET /market/{symbol}?start&end` | Daily OHLCV, market cap, daily return, source |
| `GET /market/quotes/live` | CoinGecko spot quotes (live mode only) |
| `GET /sentiment/{symbol}/daily?start&end` | Daily index, shares, counts, joined with returns; correlations |
| `GET /sentiment/{symbol}/sources?start&end` | Counts and mean score by source type and domain |
| `GET /sentiment/{symbol}/records?day` | Individual scored texts for one UTC day |
| `POST /sentiment/analyze` | Score your own text (`{"text": "...", "engine": optional}`) |
| `GET /sentiment/engines` | Engine evaluation and selection |
| `GET /forecasts/{symbol}/latest` | 1- and 3-day forecasts for every candidate, primary flagged, intervals, contributions |
| `GET /forecasts/{symbol}/history?horizon` | Stored primary forecasts with realised returns |
| `GET /backtest/{symbol}?horizon&models` | Walk-forward out-of-sample predictions |
| `GET /models/performance?symbol&horizon` | Metrics, ablation, regimes, Granger, configuration |
| `GET /models/runs` | Model run history |
| `POST /jobs/refresh` | Live fetch → score → aggregate → realise (live mode) |
| `POST /jobs/train` | Score → aggregate → train → forecast → realise |
| `GET /jobs/status` | Job state |

Every forecast row stores asset, creation time, horizon, model, run id (the model version), feature cutoff date, target date, reference price, predicted return, interval and, once the target day closes, the realised return. Forecasts are never overwritten.

## 13. Tests

```bash
cd backend && python -m pytest -q tests        # 27 tests
cd frontend && npm run typecheck && npm run lint && npm run build
```

The tests cover text cleaning, hashing and asset tagging; provider normalisation (CoinGecko day shift, open Binance candle dropped); de-duplication, relevance and future-date rejection; the causal bot filter; aggregation (equal weights, shares, missing ≠ neutral); forward-return definitions; gaps never creating returns; a **leakage test** (changing all data after day *t* leaves features at *t* unchanged); the walk-forward **embargo**; model selection; metrics; Diebold–Mariano; look-ahead-free regimes; Granger lag alignment under masking; realised-return filling; and API validation and empty states.

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs both suites on every push.

## 14. Known limitations

- The bundled text is mostly English news headlines. Only about 600 social posts are tagged BTC or ETH (150 and 470), so social sentiment is thin.
- Lexicon and small supervised engines agree only moderately with human votes (ROC-AUC around 0.6–0.7), and the votes skew positive.
- About three years of daily data per asset is short for detecting small effects, and many comparisons are reported, so read p-values with care.
- The sample ends on 2 Dec 2025. Live mode extends prices immediately, but live text history only starts when you begin collecting, so early live forecasts run with imputed sentiment (flagged on the dashboard).
- FinBERT support is implemented but optional, and wasn't run in the reference environment.
- Live provider integrations follow the providers' documented response formats and are unit-tested against those shapes. Check them on your machine with `python scripts/pipeline.py refresh-live`; failures are logged on the status page, not hidden.

## 15. Troubleshooting

| Symptom | Fix |
| --- | --- |
| Dashboard says it cannot reach the backend | Start `uvicorn main:app --port 8000` in `backend/`, or set `BACKEND_URL` in `frontend/.env.local`. |
| "No trained model yet" | Run `python scripts/pipeline.py all`. |
| SOL shows "No data" | Expected in sample mode. Use live mode and run `refresh-live` then `train`. |
| Live refresh errors (HTTP 429 or 451) | Rate-limited or region-blocked. CoinGecko is tried first and Binance second; add a free CoinGecko key or wait. |
| `database is locked` | Another pipeline run is in progress; wait for it (`python scripts/pipeline.py status`). |
| Want a clean start | Stop the backend and delete `backend/data/cryptosentinel.db*` and `backend/data/models/`, then rerun `all`. |

## 16. What changed from the original Bullseye app

Removed, because they were stock-specific or tied to paid/keyed services: the NSE screener, Ask AI (LLM chain), email alerts, Supabase auth and storage, the stock pages, the 3D landing scene, the Supabase SQL files, the stock ML artifact and scripts, and the stock workflows. Kept: the app shell, UI primitives, theme system, backend proxy, warm-up indicator, error pages and the FastAPI/slowapi/CORS setup. Everything else in the analysis pipeline and dashboard is new.

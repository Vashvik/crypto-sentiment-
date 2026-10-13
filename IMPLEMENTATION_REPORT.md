# Implementation report

## What changed from Bullseye

| | |
| --- | --- |
| **Kept** | Next.js 16 / React 19 / Tailwind 4 app, `components/ui` primitives, light/dark theme with no-flash boot script, `/api/backend` server-side proxy, backend warm-up pill, error/404 pages, FastAPI + slowapi + CORS setup |
| **Frontend modified** | Rebranded shell (new logo, header, menu, footer), navy/charcoal tokens with a blue accent and two validated chart hues, new dashboard (`components/dashboard/*`), methodology page, status page, simplified privacy/terms, locally bundled fonts |
| **Backend added** | `config`, `db` (SQLite + migrations), `market_data`, `text_processing`, `news_ingestion`, `sentiment`, `aggregation`, `features`, `evaluation`, `forecasting`, `pipeline`, `scripts/pipeline.py`, new `main.py` routes, 27 tests |
| **Stock-specific code replaced** | Yahoo/NSE price cache → crypto providers on UTC days; technical-rule signal engine and win-probability model → return forecasting with sentiment ablation; screener, Ask AI, alerts, email and Supabase auth removed |

## Status

### Completed and tested in this environment
- Clean install from the ZIP (fresh virtualenv, `npm ci`) → `pipeline.py all` completes in about 3 minutes; 27/27 backend tests pass; frontend typecheck, lint and production build pass.
- Sample-data ingestion: 4,326 price rows; 42,474 texts → 42,307 stored, 167 duplicates, 69 too short, 25 promotional, 1 non-English, 272 bot templates.
- Text classifier trained on 2,561 pre-2022 voted headlines. Engines evaluated on 5,816 validation and 1,812 test headlines; VADER + crypto lexicon selected (validation AUC 0.698).
- Daily aggregation, feature generation, walk-forward training and evaluation, ablation, regimes and Granger for BTC and ETH at 1-day and 3-day horizons; forecasts stored with full metadata.
- Two consecutive runs give identical metrics (fixed seed); earlier forecasts are kept, not overwritten.
- Every API endpoint exercised: valid input, unknown asset (404), bad dates (422), no-data and no-model states (404), sample-mode refresh (409), job lock (409 on a second job).
- Browser checks (Chromium): dashboard, methodology and status pages in dark and light themes at 1440 px and 390 px with no console errors and no horizontal scroll. Asset switch, date presets, invalid custom range, horizon toggle, headline scoring and the SOL empty state all work.
- Live-mode failure path: with no network, every provider failure is logged per source, the run completes and the dashboard keeps working on stored data.

### Implemented but not verified against the real services
- CoinGecko, Binance, RSS, CryptoPanic API and Reddit fetchers. The sandbox could not reach these hosts, and your linked computer was offline during the session. The response normalisers are unit-tested against the documented response shapes. First thing to run on your machine: set `DATA_MODE=live`, then `python scripts/pipeline.py refresh-live`, then check the **Data & model status** page.
- FinBERT engine: optional, needs `requirements-finbert.txt` and a Hugging Face download.

### Not included
- LunarCrush and CoinMarketCap (both need API keys). New providers plug into `market_data.refresh_live_prices` / `news_ingestion.refresh_live_text`.
- ARIMAX / GARCH-X and Markov-switching models from the project report. The regime analysis here uses a look-ahead-free volatility split.

## Exact commands

```bash
# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate      # Windows: py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                                     # optional
python scripts/pipeline.py all                           # init DB, load, score, aggregate, train, evaluate, forecast
python -m pytest -q tests
uvicorn main:app --port 8000

# frontend (second terminal)
cd frontend
npm ci
npm run dev                                              # open http://localhost:3000
```

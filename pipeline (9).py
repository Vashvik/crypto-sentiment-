"""Command-line entry point for the research pipeline.

Examples (run from the backend/ folder):
    python scripts/pipeline.py all                 # sample data → forecasts (offline)
    python scripts/pipeline.py all --live          # also fetch live prices + news
    python scripts/pipeline.py init-db
    python scripts/pipeline.py load-sample
    python scripts/pipeline.py refresh-live
    python scripts/pipeline.py train --engine vader
    python scripts/pipeline.py import-text my_headlines.csv
    python scripts/pipeline.py import-prices my_prices.csv
    python scripts/pipeline.py status
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import database_path, init_db  # noqa: E402
from app.services import market_data, news_ingestion, pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CryptoSentinel research pipeline")
    parser.add_argument("command", choices=["all", "init-db", "load-sample", "refresh-live", "score", "train",
                                            "import-text", "import-prices", "status"])
    parser.add_argument("path", nargs="?", help="CSV path for import-text / import-prices")
    parser.add_argument("--live", action="store_true", help="also fetch live market data and news")
    parser.add_argument("--engine", help="force a sentiment engine (vader, vader_crypto, crypto_lr, finbert)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "init-db":
        init_db(); print(f"database ready at {database_path()}"); return 0
    if args.command == "status":
        print(json.dumps(pipeline.status(), indent=2)); return 0
    if args.command == "import-text":
        init_db(); print(json.dumps(news_ingestion.import_text_csv(args.path), indent=2)); return 0
    if args.command == "import-prices":
        init_db()
        for symbol, df in market_data.load_price_csv(args.path).items():
            print(symbol, market_data.store_prices(symbol, df, "csv"), "rows")
        return 0

    steps = {
        "all": list(pipeline.STEPS),
        "load-sample": ["load-sample"],
        "refresh-live": ["refresh-live", "score", "aggregate", "realize"],
        "score": ["train-text-model", "evaluate-engines", "score", "aggregate"],
        "train": ["score", "aggregate", "train", "realize"],
    }[args.command]
    live = True if (args.live or args.command == "refresh-live") else None
    report = pipeline.run(steps, live=live, engine=args.engine)
    print(json.dumps(report, indent=2, default=str)[:20000])
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

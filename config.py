"""Central configuration. Everything tunable comes from environment variables
(see backend/.env.example) so no secret or path is hard-coded in the code."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in _env(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Asset:
    symbol: str
    name: str
    coingecko_id: str
    binance_symbol: str
    # Whole-word patterns used to tag text that arrives without coin tags
    # (RSS headlines, Reddit posts). Kept deliberately narrow: "sol" alone is
    # too common a word, so Solana needs the full name or the $SOL cashtag.
    keywords: tuple[str, ...] = field(default_factory=tuple)


ASSET_REGISTRY: dict[str, Asset] = {
    "BTC": Asset("BTC", "Bitcoin", "bitcoin", "BTCUSDT", ("bitcoin", "btc", r"\$btc", "satoshi", "sats")),
    "ETH": Asset("ETH", "Ethereum", "ethereum", "ETHUSDT", ("ethereum", "eth", r"\$eth", "ether", "vitalik")),
    "SOL": Asset("SOL", "Solana", "solana", "SOLUSDT", ("solana", r"\$sol")),
}


@dataclass(frozen=True)
class Settings:
    database_path: Path
    data_mode: str  # "sample" (bundled historical data only) or "live" (fetch from APIs too)
    assets: tuple[str, ...]
    market_providers: tuple[str, ...]
    news_sources: tuple[str, ...]
    sentiment_engine: str  # auto | vader | vader_crypto | crypto_lr | finbert
    coingecko_api_key: str
    cryptopanic_api_key: str
    reddit_client_id: str
    reddit_client_secret: str
    reddit_subreddits: tuple[str, ...]
    rss_feeds: tuple[str, ...]
    http_timeout: float
    http_retries: int
    cors_origins: tuple[str, ...]
    # Research design (all dates are UTC calendar days, inclusive)
    study_start: str
    validation_end: str
    sentiment_label_cutoff: str
    min_train_days: int
    refit_every: int
    random_seed: int


def _resolve(path: str) -> Path:
    """Relative paths are taken from the backend folder, not the shell's cwd."""
    p = Path(path)
    return p if p.is_absolute() else BACKEND_DIR / p


def load_settings() -> Settings:
    default_db = BACKEND_DIR / "data" / "cryptosentinel.db"
    return Settings(
        database_path=_resolve(_env("DATABASE_PATH", str(default_db))),
        data_mode=_env("DATA_MODE", "sample").lower(),
        assets=tuple(s.upper() for s in _env_list("ASSETS", "BTC,ETH,SOL") if s.upper() in ASSET_REGISTRY),
        market_providers=tuple(_env_list("MARKET_PROVIDERS", "coingecko,binance")),
        news_sources=tuple(_env_list("NEWS_SOURCES", "rss")),
        sentiment_engine=_env("SENTIMENT_ENGINE", "auto").lower(),
        coingecko_api_key=_env("COINGECKO_API_KEY", ""),
        cryptopanic_api_key=_env("CRYPTOPANIC_API_KEY", ""),
        reddit_client_id=_env("REDDIT_CLIENT_ID", ""),
        reddit_client_secret=_env("REDDIT_CLIENT_SECRET", ""),
        reddit_subreddits=tuple(_env_list("REDDIT_SUBREDDITS", "Bitcoin,ethereum,solana,CryptoCurrency")),
        rss_feeds=tuple(
            _env_list(
                "RSS_FEEDS",
                "https://www.coindesk.com/arc/outboundfeeds/rss/,"
                "https://cointelegraph.com/rss,"
                "https://decrypt.co/feed,"
                "https://bitcoinmagazine.com/.rss/full/",
            )
        ),
        http_timeout=float(_env("HTTP_TIMEOUT_SECONDS", "15")),
        http_retries=int(_env("HTTP_RETRIES", "3")),
        cors_origins=tuple(_env_list("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")),
        study_start=_env("STUDY_START", "2022-01-01"),
        validation_end=_env("VALIDATION_END", "2024-06-30"),
        sentiment_label_cutoff=_env("SENTIMENT_LABEL_CUTOFF", "2021-12-31"),
        min_train_days=int(_env("MIN_TRAIN_DAYS", "365")),
        refit_every=int(_env("REFIT_EVERY_DAYS", "30")),
        random_seed=int(_env("RANDOM_SEED", "42")),
    )


settings = load_settings()

SAMPLE_DIR = BACKEND_DIR / "data" / "sample"
SAMPLE_PRICES = SAMPLE_DIR / "prices_daily_coinmetrics.csv"
SAMPLE_NEWS = SAMPLE_DIR / "news_cryptopanic_btc_eth.csv.gz"
HORIZONS = (1, 3)

"""Text cleaning, de-duplication keys, language/quality filters and asset tagging."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone

from app.config import ASSET_REGISTRY

_URL = re.compile(r"https?://\S+|www\.\S+")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9 ]+")
_DIGITS = re.compile(r"\d+")

# Social sources (CryptoPanic marks tweets/Reddit posts by domain)
SOCIAL_DOMAINS = {"twitter.com", "x.com", "reddit.com", "t.me", "youtube.com"}

# Asset keyword patterns, compiled once (whole-word, case-insensitive)
_ASSET_PATTERNS = {
    symbol: re.compile(r"(?<![a-z0-9])(" + "|".join(asset.keywords) + r")(?![a-z0-9])", re.IGNORECASE)
    for symbol, asset in ASSET_REGISTRY.items()
}

# Obvious promotional / spam phrasing. Kept short and conservative.
_SPAM = re.compile(
    r"\b(giveaway|airdrop claim|free crypto|join (our|my) (telegram|discord)|promo code|referral link|100x gem)\b",
    re.IGNORECASE,
)


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(str(text))
    text = unicodedata.normalize("NFKC", text)
    text = _TAG.sub(" ", text)
    text = _URL.sub(" ", text)
    return _WS.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """Exact-duplicate key: lower-cased, punctuation removed, whitespace collapsed."""
    key = _WS.sub(" ", _NON_WORD.sub(" ", text.lower())).strip()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def template_hash(text: str) -> str:
    """Same as content_hash but with digits removed. Bot posts ('1,200 #BTC
    transferred from…', 'Price: 0.89 24h change…') collapse to one key, so a
    key repeated many times marks automated template posts."""
    key = _DIGITS.sub("", _NON_WORD.sub(" ", text.lower()))
    return hashlib.sha1(_WS.sub(" ", key).strip().encode("utf-8")).hexdigest()


def is_probably_english(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 8:
        return False
    ascii_letters = sum(1 for c in letters if c.isascii())
    return ascii_letters / len(letters) >= 0.9


def quality_issue(text: str) -> str | None:
    """Returns why a text should be excluded, or None if it is eligible."""
    if len(text.split()) < 4:
        return "too_short"
    if not is_probably_english(text):
        return "non_english"
    if _SPAM.search(text):
        return "promotional"
    return None


def tag_assets(text: str) -> set[str]:
    return {symbol for symbol, pattern in _ASSET_PATTERNS.items() if pattern.search(text)}


def source_type_for(domain: str | None, default: str = "news") -> str:
    if not domain:
        return default
    d = domain.lower().removeprefix("www.")
    return "social" if d in SOCIAL_DOMAINS or d.endswith(".reddit.com") else default


def parse_utc(value) -> datetime | None:
    """Parses a timestamp into an aware UTC datetime. Naive values are taken as UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

"""Shared HTTP client: timeouts, bounded retries with backoff, 429 handling
and a small in-memory response cache so dashboard refreshes never hammer a
free-tier API."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger("cryptosentinel.http")

USER_AGENT = "CryptoSentinel/1.0 (academic research dashboard)"
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


class ProviderError(RuntimeError):
    """Raised when an external provider cannot return usable data."""


def get(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    ttl: float = 0,
    expect: str = "json",
    retries: int | None = None,
) -> Any:
    key = f"{url}?{sorted((params or {}).items())}|{expect}"
    if ttl:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]

    attempts = (settings.http_retries if retries is None else retries) + 1
    merged_headers = {"User-Agent": USER_AGENT, "Accept": "application/json" if expect == "json" else "*/*"}
    merged_headers.update(headers or {})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=settings.http_timeout, follow_redirects=True) as client:
                resp = client.get(url, params=params, headers=merged_headers)
            if resp.status_code == 429:
                wait = min(float(resp.headers.get("Retry-After", 2 ** (attempt + 1))), 60.0)
                last_error = ProviderError(f"rate limited by {httpx.URL(url).host} (HTTP 429)")
                log.warning("429 from %s, waiting %.0fs", url, wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                last_error = ProviderError(f"{httpx.URL(url).host} returned HTTP {resp.status_code}")
                time.sleep(2 ** attempt)
                continue
            if resp.status_code >= 400:
                raise ProviderError(f"{httpx.URL(url).host} returned HTTP {resp.status_code}")
            data = resp.json() if expect == "json" else resp.text
            if ttl:
                with _cache_lock:
                    _cache[key] = (time.time(), data)
            return data
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            last_error = ProviderError(f"request to {httpx.URL(url).host} failed: {type(exc).__name__}")
            time.sleep(min(2 ** attempt, 8))
    raise last_error or ProviderError(f"request to {url} failed")


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()

"""StockTwits ticker-mention scraper (public API, no key required).

Pulls the trending-symbols list, then counts messages posted in the last
24 hours on each trending symbol's stream. Sleeps between per-symbol calls
and backs off on HTTP 429.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

import config

log = logging.getLogger(__name__)

BASE_URL = "https://api.stocktwits.com/api/2"
HEADERS = {"User-Agent": "buzz-screener/1.0"}


def _get(url: str, retries: int = 1) -> dict | None:
    """GET with a single 60s-backoff retry on 429 rate limiting.

    Uses urllib rather than requests: StockTwits' bot filtering 403s the
    requests library's client fingerprint but accepts urllib and curl.
    """
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                log.warning(
                    "Rate limited by StockTwits, backing off %.0fs",
                    config.STOCKTWITS_RATE_LIMIT_BACKOFF,
                )
                time.sleep(config.STOCKTWITS_RATE_LIMIT_BACKOFF)
                continue
            log.warning("StockTwits returned %d for %s", exc.code, url)
            return None
        except Exception:
            log.exception("Request failed: %s", url)
            return None
    return None


def trending_symbols() -> list[str]:
    data = _get(f"{BASE_URL}/trending/symbols.json")
    if not data:
        return []
    symbols = []
    for sym in data.get("symbols", []):
        ticker = sym.get("symbol", "")
        # Skip crypto/forex style symbols like BTC.X
        if ticker and "." not in ticker and ticker not in config.TICKER_BLACKLIST:
            symbols.append(ticker)
    return symbols


def _messages_last_24h(symbol: str) -> int:
    data = _get(f"{BASE_URL}/streams/symbol/{symbol}.json")
    if not data:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = 0
    for msg in data.get("messages", []):
        created = msg.get("created_at", "")
        try:
            when = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        if when >= cutoff:
            count += 1
    return count


def scrape() -> Counter:
    """Mention counts per ticker from StockTwits trending streams."""
    counts: Counter = Counter()
    symbols = trending_symbols()
    log.info("StockTwits trending symbols: %d", len(symbols))

    for symbol in symbols:
        n = _messages_last_24h(symbol)
        if n:
            counts[symbol] += n
        time.sleep(config.STOCKTWITS_SLEEP)

    return counts

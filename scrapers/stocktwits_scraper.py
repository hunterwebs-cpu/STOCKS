import re
import time
from collections import defaultdict
from typing import Dict

import requests

import config

_BASE_URL = "https://api.stocktwits.com/api/2"
_TICKER_RE = re.compile(r'\$([A-Z]{1,5})\b')
_TRENDING_LIMIT = 30


def _extract_tickers(text: str) -> list:
    if not text:
        return []
    return [
        m for m in _TICKER_RE.findall(text)
        if m not in config.TICKER_BLACKLIST
    ]


def _get_trending_symbols() -> list:
    """Fetch the current trending symbols from StockTwits."""
    try:
        resp = requests.get(f"{_BASE_URL}/trending/symbols.json", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            symbols = [s["symbol"] for s in data.get("symbols", [])]
            return symbols[:_TRENDING_LIMIT]
    except Exception as e:
        print(f"[stocktwits] Failed to fetch trending symbols: {e}")
    return []


def _get_symbol_stream(symbol: str) -> list:
    """Fetch the message stream for a specific symbol."""
    try:
        resp = requests.get(
            f"{_BASE_URL}/streams/symbol/{symbol}.json",
            timeout=10,
        )
        if resp.status_code == 429:
            print(f"[stocktwits] Rate limited on {symbol}, backing off 60s")
            time.sleep(60)
            resp = requests.get(
                f"{_BASE_URL}/streams/symbol/{symbol}.json",
                timeout=10,
            )
        if resp.status_code == 200:
            return resp.json().get("messages", [])
    except Exception as e:
        print(f"[stocktwits] Failed to fetch stream for {symbol}: {e}")
    return []


def scrape_stocktwits() -> Dict[str, int]:
    """
    Pull trending symbols from StockTwits and count $TICKER mentions
    in their message streams.
    Returns a dict of {ticker: mention_count}.
    """
    counts: Dict[str, int] = defaultdict(int)

    trending = _get_trending_symbols()
    if not trending:
        print("[stocktwits] No trending symbols returned; skipping")
        return counts

    for symbol in trending:
        messages = _get_symbol_stream(symbol)
        for msg in messages:
            body = msg.get("body", "")
            for ticker in _extract_tickers(body):
                counts[ticker] += 1
        time.sleep(0.5)

    return dict(counts)

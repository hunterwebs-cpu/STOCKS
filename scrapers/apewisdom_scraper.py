"""ApeWisdom scraper — Reddit ticker mentions without the Reddit API.

ApeWisdom (https://apewisdom.io) aggregates ticker mention counts across the
major investing subreddits (r/wallstreetbets, r/stocks, r/investing,
r/options, r/pennystocks, r/stockmarket and more) and republishes them via a
free, keyless JSON API. This provides the Reddit-buzz signal while direct
Reddit API access is unavailable or pending approval.

Endpoint: https://apewisdom.io/api/v1.0/filter/{filter}/page/{n}
`mentions` in each result is the trailing-24h mention count.
"""

import logging
import re
import time
from collections import Counter

import requests

import config

log = logging.getLogger(__name__)

BASE_URL = "https://apewisdom.io/api/v1.0/filter/{flt}/page/{page}"
HEADERS = {"User-Agent": "buzz-screener/1.0"}
TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def scrape() -> Counter:
    """24h Reddit mention counts per ticker, all pages of the configured filter."""
    counts: Counter = Counter()
    page = 1
    total_pages = 1

    while page <= total_pages:
        url = BASE_URL.format(flt=config.APEWISDOM_FILTER, page=page)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException:
            log.exception("ApeWisdom request failed: %s", url)
            break
        if resp.status_code != 200:
            log.warning("ApeWisdom returned %d for %s", resp.status_code, url)
            break

        data = resp.json()
        total_pages = int(data.get("pages", 1))

        for item in data.get("results", []):
            ticker = (item.get("ticker") or "").upper()
            mentions = item.get("mentions")
            if not TICKER_RE.match(ticker) or ticker in config.TICKER_BLACKLIST:
                continue
            try:
                mentions = int(mentions)
            except (TypeError, ValueError):
                continue
            if mentions > 0:
                counts[ticker] += mentions

        page += 1
        time.sleep(config.APEWISDOM_SLEEP)

    log.info("ApeWisdom: %d tickers across %d page(s)", len(counts), page - 1)
    return counts

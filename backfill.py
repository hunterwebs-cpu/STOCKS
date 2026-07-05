#!/usr/bin/env python3
"""One-shot baseline backfill from ApeWisdom's mentions_24h_ago field.

ApeWisdom exposes, for every ticker, the mention count for the 24h window
before the current one. That lets us seed exactly one prior day of history
at the same scale as the nightly apewisdom source, so the z-score baseline
gets a one-day head start.

Idempotent: skips seeding if the target date already has apewisdom rows.
"""

import logging
import re
import time
from collections import Counter
from datetime import timedelta

import requests

import config
from db.store import MentionStore
from run_nightly import today_eastern

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("backfill")

TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def fetch_yesterday_counts() -> Counter:
    counts: Counter = Counter()
    page, total_pages = 1, 1
    while page <= total_pages:
        url = f"https://apewisdom.io/api/v1.0/filter/{config.APEWISDOM_FILTER}/page/{page}"
        resp = requests.get(url, headers={"User-Agent": "buzz-screener/1.0"}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        total_pages = int(data.get("pages", 1))
        for item in data.get("results", []):
            ticker = (item.get("ticker") or "").upper()
            if not TICKER_RE.match(ticker) or ticker in config.TICKER_BLACKLIST:
                continue
            try:
                prior = int(item.get("mentions_24h_ago") or 0)
            except (TypeError, ValueError):
                continue
            if prior > 0:
                counts[ticker] += prior
        page += 1
        time.sleep(config.APEWISDOM_SLEEP)
    return counts


def main():
    yesterday = (today_eastern() - timedelta(days=1)).isoformat()
    with MentionStore(config.DB_PATH) as store:
        existing = store.conn.execute(
            "SELECT 1 FROM mentions WHERE date = ? AND source = 'apewisdom' LIMIT 1",
            (yesterday,),
        ).fetchone()
        if existing:
            log.info("%s already has apewisdom data — nothing to backfill", yesterday)
            return
        counts = fetch_yesterday_counts()
        store.upsert_mentions(yesterday, "apewisdom", dict(counts))
        log.info("Backfilled %s: %d tickers seeded from mentions_24h_ago",
                 yesterday, len(counts))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Nightly buzz screener orchestrator.

Pipeline:
    1. Scrape Reddit + StockTwits for today's ticker mention counts
    2. Persist counts to SQLite (per source, upsert-safe on re-run)
    3. Z-score today's counts against each ticker's 30-day baseline
    4. Pull RSI(21) for every flagged ticker via yfinance
    5. Write the report to reports/output/ and email it via SMTP

Run via cron ~8pm ET on trading-day eves (see README).
"""

import logging
import sys
from datetime import date
from pathlib import Path

import config
from analyzer import buzz_detector, technical
from db.store import MentionStore
from reports import emailer, formatter
from scrapers import reddit_scraper, stocktwits_scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("run_nightly")


def scrape_all() -> dict[str, dict[str, int]]:
    """Run every scraper, tolerating individual failures."""
    results: dict[str, dict[str, int]] = {}

    try:
        results["reddit"] = dict(reddit_scraper.scrape())
        log.info("Reddit: %d tickers mentioned", len(results["reddit"]))
    except Exception:
        log.exception("Reddit scrape failed")

    try:
        results["stocktwits"] = dict(stocktwits_scraper.scrape())
        log.info("StockTwits: %d tickers mentioned", len(results["stocktwits"]))
    except Exception:
        log.exception("StockTwits scrape failed")

    return results


def main() -> int:
    today = date.today().isoformat()
    log.info("Nightly buzz screener starting for %s", today)

    source_counts = scrape_all()
    if not source_counts:
        log.error("All scrapers failed — nothing to store, aborting")
        return 1

    with MentionStore(config.DB_PATH) as store:
        for source, counts in source_counts.items():
            store.upsert_mentions(today, source, counts)

        hits = buzz_detector.detect(store, today)

    rows = []
    for hit in hits:
        rsi_val = technical.rsi(hit.ticker)
        zone = technical.rsi_zone(rsi_val)
        rows.append(
            {
                "ticker": hit.ticker,
                "z_score": hit.z_score,
                "mentions": hit.mentions,
                "baseline_avg": hit.baseline_avg,
                "rsi": rsi_val,
                "rsi_zone": zone,
                "signal": technical.signal_for_zone(zone),
            }
        )

    report = formatter.build_report(today, rows)
    print(report)

    report_dir = Path(config.REPORT_DIR)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"buzz_report_{today}.txt"
    report_path.write_text(report)
    log.info("Report saved to %s", report_path)

    emailer.send_report(today, report)

    log.info("Done — %d tickers flagged", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())

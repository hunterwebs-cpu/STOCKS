#!/usr/bin/env python3
"""
Nightly buzz screener entry point.

Typical usage:
    python run_nightly.py

Cron (8pm ET, Mon–Thu):
    0 20 * * 1-4 cd /path/to/STOCKS && python run_nightly.py >> logs/nightly.log 2>&1
"""
import datetime
import os
import sys

import config
from db import store
from scrapers.reddit_scraper import scrape_reddit
from scrapers.stocktwits_scraper import scrape_stocktwits
from analyzer.buzz_detector import detect_buzz
from analyzer.technical import get_technical
from reports.formatter import build_report
from reports.emailer import send_report


def main() -> None:
    today = datetime.date.today().isoformat()
    print(f"[run_nightly] Starting buzz scan for {today}")

    # 1. Initialize DB
    store.init_db()

    # 2. Scrape sources
    print("[run_nightly] Scraping Reddit...")
    reddit_counts = scrape_reddit()
    print(f"[run_nightly] Reddit: {len(reddit_counts)} unique tickers found")

    print("[run_nightly] Scraping StockTwits...")
    st_counts = scrape_stocktwits()
    print(f"[run_nightly] StockTwits: {len(st_counts)} unique tickers found")

    # 3. Merge counts from both sources
    merged: dict = {}
    for ticker, count in reddit_counts.items():
        merged[ticker] = merged.get(ticker, 0) + count
    for ticker, count in st_counts.items():
        merged[ticker] = merged.get(ticker, 0) + count

    print(f"[run_nightly] Total merged: {len(merged)} unique tickers")

    # 4. Persist today's counts
    store.upsert_mentions(today, merged)

    # 5. Detect buzz signals
    print("[run_nightly] Running buzz detection...")
    signals = detect_buzz(today)
    print(f"[run_nightly] Flagged tickers: {len(signals)}")

    # 6. Pull technical data for each flagged ticker
    technical_map = {}
    for sig in signals:
        print(f"[run_nightly] Fetching RSI for {sig.ticker}...")
        technical_map[sig.ticker] = get_technical(sig.ticker)

    # 7. Build report text
    report_text = build_report(today, signals, technical_map)
    print("\n" + report_text)

    # 8. Save report to file
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    report_filename = os.path.join(config.REPORT_DIR, f"buzz_report_{today}.txt")
    with open(report_filename, "w") as f:
        f.write(report_text)
    print(f"[run_nightly] Report saved to {report_filename}")

    # 9. Email report
    subject = f"{config.EMAIL_SUBJECT} — {today}"
    send_report(subject, report_text)

    print("[run_nightly] Done.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[run_nightly] Interrupted.")
        sys.exit(0)
    except Exception as e:
        print(f"[run_nightly] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

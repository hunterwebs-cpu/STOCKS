#!/usr/bin/env python3
"""Nightly buzz screener orchestrator.

Pipeline:
    1. Scrape Reddit + StockTwits for today's ticker mention counts
    2. Persist counts to SQLite (per source, upsert-safe on re-run)
    3. Z-score today's counts against each ticker's 30-day baseline
    4. Pull RSI(21) for every flagged ticker via the Yahoo Finance chart API
    5. Write the report to reports/output/ and email it via SMTP

Run via cron ~8pm ET on trading-day eves (see README).
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config
from analyzer import buzz_detector, short_interest, technical
from db.store import MentionStore
from reports import emailer, formatter, html_formatter
from scrapers import apewisdom_scraper, reddit_scraper, stocktwits_scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("run_nightly")


def today_eastern():
    """Report date in US Eastern time, so the ~8pm ET run is labeled with
    the evening's date regardless of the container's (UTC) clock."""
    return datetime.now(ZoneInfo("America/New_York")).date()


def scrape_all() -> dict[str, dict[str, int]]:
    """Run every scraper, tolerating individual failures."""
    results: dict[str, dict[str, int]] = {}

    if config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET:
        try:
            results["reddit"] = dict(reddit_scraper.scrape())
            log.info("Reddit: %d tickers mentioned", len(results["reddit"]))
        except Exception:
            log.exception("Reddit scrape failed")
    else:
        log.info("Reddit API credentials not set — skipping direct Reddit scrape")

    if config.APEWISDOM_ENABLED:
        try:
            results["apewisdom"] = dict(apewisdom_scraper.scrape())
            log.info("ApeWisdom: %d tickers mentioned", len(results["apewisdom"]))
        except Exception:
            log.exception("ApeWisdom scrape failed")

    try:
        results["stocktwits"] = dict(stocktwits_scraper.scrape())
        log.info("StockTwits: %d tickers mentioned", len(results["stocktwits"]))
    except Exception:
        log.exception("StockTwits scrape failed")

    return results


def main() -> int:
    today = today_eastern().isoformat()
    # Runs fire ~1am ET, after the trading-day-eve buzz already happened —
    # so the report is labeled with the date the data is actually about
    # (the evening before this run), not the run's own calendar date.
    data_date = (today_eastern() - timedelta(days=1)).isoformat()
    log.info("Nightly buzz screener starting for %s (data for %s)", today, data_date)

    source_counts = scrape_all()
    if not source_counts:
        log.error("All scrapers failed — nothing to store, aborting")
        return 1

    mentioned_today = set().union(*(c.keys() for c in source_counts.values()))

    with MentionStore(config.DB_PATH) as store:
        for source, counts in source_counts.items():
            store.upsert_mentions(today, source, counts)

        # Daily FINRA short-volume ratios for every ticker we track — this
        # history is what lets the report show covering-vs-pressing trends.
        finra = short_interest.latest_short_volume()
        if finra:
            trade_date, ratios = finra
            tracked = {t: r for t, r in ratios.items() if t in mentioned_today}
            store.upsert_short_volume(trade_date, tracked)
            log.info("Stored short-volume ratios for %d tracked tickers (%s)",
                     len(tracked), trade_date)

        hits = buzz_detector.detect(store, today)
        movers = buzz_detector.top_movers(
            store, today, n=config.TOP_MOVERS_COUNT,
            min_mentions=config.TOP_MOVERS_MIN_MENTIONS,
        )
        sv_history = {
            h.ticker: store.short_volume_history(h.ticker) for h in hits
        }

    short_stats = short_interest.finviz_stats_bulk([h.ticker for h in hits])

    rows = []
    for hit in hits:
        rsi_val = technical.rsi(hit.ticker)
        zone = technical.rsi_zone(rsi_val)
        stats = short_stats.get(hit.ticker, {})
        short_float = stats.get("short_float_pct")
        dtc = stats.get("days_to_cover")
        squeeze = short_float is not None and (
            short_float >= config.SQUEEZE_SHORT_FLOAT_PCT
            or (short_float >= config.SQUEEZE_ALT_SHORT_FLOAT_PCT
                and (dtc or 0) >= config.SQUEEZE_ALT_DTC)
        )
        rows.append(
            {
                "ticker": hit.ticker,
                "z_score": hit.z_score,
                "mentions": hit.mentions,
                "baseline_avg": hit.baseline_avg,
                "rsi": rsi_val,
                "rsi_zone": zone,
                "signal": technical.signal_for_zone(zone),
                "short_float": short_float,
                "days_to_cover": dtc,
                "sv_trend": short_interest.short_volume_trend(
                    sv_history.get(hit.ticker, [])
                ),
                "squeeze": squeeze,
            }
        )

    flagged_tickers = {h.ticker for h in hits}
    mover_rows = [
        {
            "ticker": m.ticker,
            "mentions": m.mentions,
            "baseline_avg": m.baseline_avg,
            "z_score": m.z_score,
            "pct_change": (
                round((m.mentions - m.baseline_avg) / m.baseline_avg * 100, 0)
                if m.baseline_avg > 0 else None
            ),
            "flagged": m.ticker in flagged_tickers,
        }
        for m in movers
    ]

    report = formatter.build_report(data_date, rows, mover_rows)
    html_report = html_formatter.build_html_report(data_date, rows, mover_rows)
    print(report)

    report_dir = Path(config.REPORT_DIR)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"buzz_report_{data_date}.txt"
    report_path.write_text(report)
    (report_dir / f"buzz_report_{data_date}.html").write_text(html_report)
    log.info("Reports saved to %s", report_dir)

    emailer.send_report(data_date, report, html_report)

    log.info("Done — %d tickers flagged", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())

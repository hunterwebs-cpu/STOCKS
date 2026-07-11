"""Short-interest data for squeeze detection — all keyless sources.

Two complementary feeds:

1. Finviz quote pages: short float % and days-to-cover (short ratio).
   Snapshot of the latest bi-monthly exchange short interest report, so it
   lags reality by up to ~2 weeks — treat it as the structural setup, not
   a live reading. Fetched only for flagged tickers (one page per ticker).

2. FINRA Reg SHO daily short sale volume files: per-symbol short volume /
   total volume for every trading day, published nightly. This is the
   *trajectory* signal — a rising short-volume ratio while a stock buzzes
   means shorts are still pressing (or being replaced) rather than covering.
"""

import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

import config

log = logging.getLogger(__name__)

FINVIZ_URL = "https://finviz.com/quote.ashx?t={ticker}"
FINRA_URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{yyyymmdd}.txt"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Values are sometimes wrapped in a coloring span: <b><span ...>29.83%</span></b>
_FINVIZ_FIELDS = {
    "short_float_pct": r"Short Float.*?<b>(?:<span[^>]*>)?([^<]+)",
    "days_to_cover": r"Short Ratio.*?<b>(?:<span[^>]*>)?([^<]+)",
}


def _to_float(raw: str) -> float | None:
    raw = raw.strip().rstrip("%")
    try:
        return float(raw)
    except ValueError:
        return None


def finviz_stats(ticker: str) -> dict:
    """Short float %% and days-to-cover for one ticker (None when unknown)."""
    out = {"short_float_pct": None, "days_to_cover": None}
    try:
        req = urllib.request.Request(FINVIZ_URL.format(ticker=ticker), headers=UA)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", "ignore")
    except Exception:
        log.warning("Finviz fetch failed for %s", ticker)
        return out
    for key, pattern in _FINVIZ_FIELDS.items():
        m = re.search(pattern, html, re.S)
        if m:
            out[key] = _to_float(m.group(1))
    return out


def finviz_stats_bulk(tickers: list[str]) -> dict[str, dict]:
    stats = {}
    for t in tickers:
        stats[t] = finviz_stats(t)
        time.sleep(config.FINVIZ_SLEEP)
    return stats


def _fetch_finra_file(day: date) -> dict[str, float] | None:
    url = FINRA_URL.format(yyyymmdd=day.strftime("%Y%m%d"))
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):  # weekend/holiday — CDN has no file
            return None
        log.warning("FINRA file for %s returned %d", day, exc.code)
        return None
    except Exception:
        log.exception("FINRA fetch failed for %s", day)
        return None

    ratios: dict[str, float] = {}
    for line in text.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < 5:
            continue
        symbol = parts[1]
        try:
            short_vol = float(parts[2])
            total_vol = float(parts[4])
        except ValueError:
            continue
        if total_vol > 0:
            ratios[symbol] = round(short_vol / total_vol, 4)
    return ratios


def latest_short_volume(max_back: int = 5) -> tuple[str, dict[str, float]] | None:
    """Most recent FINRA daily short-volume ratios, walking back over
    weekends/holidays. Returns (trade_date_iso, {symbol: ratio})."""
    day = date.today()
    for _ in range(max_back):
        ratios = _fetch_finra_file(day)
        if ratios:
            log.info("FINRA short volume for %s: %d symbols", day, len(ratios))
            return day.isoformat(), ratios
        day -= timedelta(days=1)
    log.warning("No FINRA short-volume file found in last %d days", max_back)
    return None


def short_volume_trend(history: list[tuple[str, float]]) -> float | None:
    """Change in short-volume ratio: mean of the latest half of the window
    minus mean of the earlier half. Positive = shorting pressure rising.
    Needs at least 4 data points."""
    if len(history) < 4:
        return None
    ratios = [r for _, r in sorted(history)]
    mid = len(ratios) // 2
    return round(sum(ratios[mid:]) / len(ratios[mid:])
                 - sum(ratios[:mid]) / mid, 4)

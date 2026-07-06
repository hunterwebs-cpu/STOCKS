"""RSI on the daily timeframe, from Yahoo Finance's chart API.

Fetches daily closes straight from the public chart endpoint with urllib
(the yfinance library's curl_cffi backend cannot traverse the Claude Code
cloud egress proxy, and this endpoint needs no cookie/crumb dance), then
computes classic Wilder-smoothed RSI.
"""

import json
import logging
import urllib.error
import urllib.request

import numpy as np

import config

log = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=6mo&interval=1d"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Zones: <30 OVERSOLD, 30–40 WEAK, 40–60 NEUTRAL, 60–70 STRONG, >70 OVERBOUGHT
RSI_ZONES = [
    (30, "OVERSOLD"),
    (40, "WEAK"),
    (60, "NEUTRAL"),
]

ZONE_SIGNALS = {
    "OVERSOLD": "BUZZ + OVERSOLD — Watch for reversal",
    "WEAK": "BUZZ + WEAK — Early interest, still soft",
    "NEUTRAL": "BUZZ + NEUTRAL — Building momentum",
    "STRONG": "BUZZ + STRONG — Momentum running",
    "OVERBOUGHT": "BUZZ + OVERBOUGHT — Extended, chase risk",
    "N/A": "BUZZ — RSI unavailable",
}


def _daily_closes(ticker: str) -> list[float]:
    req = urllib.request.Request(CHART_URL.format(ticker=ticker), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return []
    quote = (result[0].get("indicators") or {}).get("quote") or [{}]
    closes = quote[0].get("close") or []
    return [c for c in closes if c is not None]


def rsi(ticker: str, period: int | None = None) -> float | None:
    """Latest Wilder RSI(period) from daily closes, or None if unavailable."""
    period = period or config.RSI_PERIOD
    try:
        closes = _daily_closes(ticker)
    except urllib.error.HTTPError as exc:
        log.warning("Yahoo chart API returned %d for %s", exc.code, ticker)
        return None
    except Exception:
        log.exception("Price fetch failed for %s", ticker)
        return None

    if len(closes) < period + 1:
        log.warning("Not enough price history for %s RSI(%d)", ticker, period)
        return None

    deltas = np.diff(np.asarray(closes, dtype=float))
    gains = np.clip(deltas, 0, None)
    losses = np.clip(-deltas, 0, None)

    # Wilder: seed with a simple average, then recursive smoothing
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def rsi_zone(value: float | None) -> str:
    if value is None:
        return "N/A"
    for upper, zone in RSI_ZONES:
        if value < upper:
            return zone
    return "STRONG" if value <= 70 else "OVERBOUGHT"


def signal_for_zone(zone: str) -> str:
    return ZONE_SIGNALS.get(zone, ZONE_SIGNALS["N/A"])

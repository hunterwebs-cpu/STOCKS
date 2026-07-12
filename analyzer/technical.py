"""Price stats — RSI, 52-week range, and previous close — from one Yahoo
Finance chart API call per ticker (no key, proxy-friendly).

yfinance's curl_cffi backend cannot traverse the Claude Code cloud egress
proxy, so we hit the public v8/finance/chart endpoint directly with
urllib. A single 1-year daily fetch serves RSI's warm-up window, a
genuine 52-week high/low, and the latest close — one request per ticker
instead of one per metric.
"""

import json
import logging
import urllib.error
import urllib.request

import numpy as np

import config

log = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
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


def _fetch_ohlc(ticker: str) -> dict:
    req = urllib.request.Request(CHART_URL.format(ticker=ticker), headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return {"close": [], "high": [], "low": []}
    quote = (result[0].get("indicators") or {}).get("quote") or [{}]
    return {
        "close": [c for c in quote[0].get("close", []) if c is not None],
        "high": [h for h in quote[0].get("high", []) if h is not None],
        "low": [l for l in quote[0].get("low", []) if l is not None],
    }


def _wilder_rsi(closes: list[float], period: int) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = np.diff(np.asarray(closes, dtype=float))
    gains = np.clip(deltas, 0, None)
    losses = np.clip(-deltas, 0, None)
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


def fetch_price_data(ticker: str, rsi_period: int | None = None) -> dict:
    """RSI(period), 52-week high/low, and the latest available close.

    This job runs before market open, so the most recent daily close IS
    the "previous close" for the trading session ahead.
    """
    rsi_period = rsi_period or config.RSI_PERIOD
    out = {
        "rsi": None, "rsi_zone": "N/A",
        "high_52w": None, "low_52w": None, "prev_close": None,
    }
    try:
        ohlc = _fetch_ohlc(ticker)
    except urllib.error.HTTPError as exc:
        log.warning("Yahoo chart API returned %d for %s", exc.code, ticker)
        return out
    except Exception:
        log.exception("Price fetch failed for %s", ticker)
        return out

    closes, highs, lows = ohlc["close"], ohlc["high"], ohlc["low"]
    if closes:
        out["prev_close"] = round(closes[-1], 2)
    if highs:
        out["high_52w"] = round(max(highs), 2)
    if lows:
        out["low_52w"] = round(min(lows), 2)

    if len(closes) < rsi_period + 1:
        log.warning("Not enough price history for %s RSI(%d)", ticker, rsi_period)
    out["rsi"] = _wilder_rsi(closes, rsi_period)
    out["rsi_zone"] = rsi_zone(out["rsi"])
    return out

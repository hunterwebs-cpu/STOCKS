"""RSI on the daily timeframe via yfinance (Wilder's smoothing)."""

import logging

import yfinance as yf

import config

log = logging.getLogger(__name__)

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


def rsi(ticker: str, period: int | None = None) -> float | None:
    """Latest RSI(period) from daily closes, or None if data is unavailable."""
    period = period or config.RSI_PERIOD
    try:
        data = yf.Ticker(ticker).history(period="6mo", interval="1d")
    except Exception:
        log.exception("yfinance fetch failed for %s", ticker)
        return None

    closes = data.get("Close")
    if closes is None:
        return None
    closes = closes.dropna()
    if len(closes) < period + 1:
        log.warning("Not enough price history for %s RSI(%d)", ticker, period)
        return None

    delta = closes.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    # Wilder's smoothing == EMA with alpha = 1/period
    avg_gain = gains.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period).mean()

    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
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

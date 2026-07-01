from dataclasses import dataclass
from typing import Optional

import numpy as np
import yfinance as yf

import config


@dataclass
class TechnicalData:
    ticker: str
    rsi: Optional[float]
    rsi_zone: str
    signal_label: str


def _compute_rsi(closes: np.ndarray, period: int) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _rsi_zone(rsi: float) -> str:
    if rsi < config.RSI_ZONE_OVERSOLD:
        return "OVERSOLD"
    if rsi < config.RSI_ZONE_WEAK:
        return "WEAK"
    if rsi < config.RSI_ZONE_NEUTRAL:
        return "NEUTRAL"
    if rsi < config.RSI_ZONE_STRONG:
        return "STRONG"
    return "OVERBOUGHT"


def _signal_label(zone: str) -> str:
    labels = {
        "OVERSOLD":   "BUZZ + OVERSOLD — Watch for reversal",
        "WEAK":       "BUZZ + WEAK — Potential recovery setup",
        "NEUTRAL":    "BUZZ + NEUTRAL — Building momentum",
        "STRONG":     "BUZZ + STRONG — Momentum extended",
        "OVERBOUGHT": "BUZZ + OVERBOUGHT — Caution, extended",
    }
    return labels.get(zone, "BUZZ — RSI unavailable")


def get_technical(ticker: str) -> TechnicalData:
    """Download daily OHLCV via yfinance and compute RSI(21)."""
    try:
        data = yf.download(
            ticker,
            period="90d",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if data.empty or len(data) < config.RSI_PERIOD + 1:
            raise ValueError("insufficient data")

        closes = data["Close"].values.flatten().astype(float)
        rsi = _compute_rsi(closes, config.RSI_PERIOD)
        if rsi is None:
            raise ValueError("RSI computation failed")

        zone = _rsi_zone(rsi)
        return TechnicalData(
            ticker=ticker,
            rsi=round(rsi, 1),
            rsi_zone=zone,
            signal_label=_signal_label(zone),
        )
    except Exception as e:
        print(f"[technical] Could not compute RSI for {ticker}: {e}")
        return TechnicalData(
            ticker=ticker,
            rsi=None,
            rsi_zone="UNKNOWN",
            signal_label="BUZZ — RSI unavailable",
        )

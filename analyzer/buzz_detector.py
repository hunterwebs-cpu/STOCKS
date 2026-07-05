"""Z-score buzz detection.

For each ticker mentioned today, compares today's total mention count
against its rolling baseline (mean/std over the prior N run days, today
excluded). Tickers at or above the configured z threshold are flagged.
"""

import logging
from dataclasses import dataclass

import numpy as np

import config
from db.store import MentionStore

log = logging.getLogger(__name__)


@dataclass
class BuzzHit:
    ticker: str
    z_score: float
    mentions: int
    baseline_avg: float


def z_score(today: int, history: list[int]) -> float:
    """z = (today - mean) / std over the prior-day history.

    The std is floored at max(1, 10% of the mean): a quiet ticker jumping
    off a flat baseline still scores (0,0,0 -> 6 gives z = 6), while a
    near-flat high-volume baseline can't turn a small relative bump into
    a huge z (500-ish -> 510 stays under threshold).
    """
    arr = np.asarray(history, dtype=float)
    mean = arr.mean()
    std = max(arr.std(), 1.0, 0.1 * mean)
    return float((today - mean) / std)


def detect(store: MentionStore, date: str) -> list[BuzzHit]:
    """Flag tickers whose mentions today spike >= threshold sigma above baseline."""
    today_counts = store.totals_for_date(date)
    baseline_dates = store.baseline_dates(date, config.BASELINE_DAYS)

    if len(baseline_dates) < config.MIN_HISTORY_DAYS:
        log.warning(
            "Only %d prior run days recorded (need %d) — no tickers flagged yet. "
            "Baseline is still building.",
            len(baseline_dates),
            config.MIN_HISTORY_DAYS,
        )
        return []

    hits: list[BuzzHit] = []
    for ticker, today in today_counts.items():
        if today < config.MIN_MENTIONS_TODAY:
            continue
        history = store.history(ticker, baseline_dates)

        # Require the ticker itself to have some track record so a
        # first-ever mention doesn't auto-flag off an all-zero baseline.
        first = store.first_seen(ticker)
        if first is None or first >= date:
            continue

        z = z_score(today, history)
        if z >= config.Z_SCORE_THRESHOLD:
            hits.append(
                BuzzHit(
                    ticker=ticker,
                    z_score=round(z, 2),
                    mentions=today,
                    baseline_avg=round(float(np.mean(history)), 1),
                )
            )

    hits.sort(key=lambda h: h.z_score, reverse=True)
    log.info("Flagged %d tickers at z >= %.2f", len(hits), config.Z_SCORE_THRESHOLD)
    return hits

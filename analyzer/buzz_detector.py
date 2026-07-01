from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

import config
from db import store


@dataclass
class BuzzSignal:
    ticker: str
    today_mentions: int
    baseline_mean: float
    baseline_std: float
    z_score: float


def _compute_z_score(today: int, history_counts: List[int]) -> Optional[float]:
    if len(history_counts) < config.MIN_HISTORY_DAYS:
        return None
    arr = np.array(history_counts, dtype=float)
    mean = arr.mean()
    std = arr.std()
    if std == 0:
        return None
    return float((today - mean) / std)


def detect_buzz(today: str) -> List[BuzzSignal]:
    """
    For every ticker that has today's mentions AND sufficient history,
    compute z-score and return those at or above the configured threshold.
    """
    today_counts: Dict[str, int] = store.get_today_counts(today)
    if not today_counts:
        return []

    signals: List[BuzzSignal] = []

    for ticker, today_count in today_counts.items():
        history = store.get_history(
            ticker=ticker,
            before_date=today,
            window_days=config.BASELINE_WINDOW_DAYS,
        )
        if len(history) < config.MIN_HISTORY_DAYS:
            continue

        history_counts = [count for _, count in history]
        z = _compute_z_score(today_count, history_counts)
        if z is None or z < config.BUZZ_Z_THRESHOLD:
            continue

        arr = np.array(history_counts, dtype=float)
        signals.append(BuzzSignal(
            ticker=ticker,
            today_mentions=today_count,
            baseline_mean=float(arr.mean()),
            baseline_std=float(arr.std()),
            z_score=z,
        ))

    signals.sort(key=lambda s: s.z_score, reverse=True)
    return signals

import sqlite3
import datetime
from typing import Dict, List, Tuple, Optional
import config


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticker_mentions (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker  TEXT    NOT NULL,
                date    TEXT    NOT NULL,
                count   INTEGER NOT NULL DEFAULT 0,
                UNIQUE(ticker, date)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticker_date
            ON ticker_mentions(ticker, date)
        """)


def upsert_mentions(date: str, counts: Dict[str, int]) -> None:
    """Insert or add to mention counts for a given date."""
    with _connect() as conn:
        for ticker, count in counts.items():
            conn.execute("""
                INSERT INTO ticker_mentions (ticker, date, count)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker, date) DO UPDATE SET count = count + excluded.count
            """, (ticker, date, count))


def get_history(
    ticker: str,
    before_date: str,
    window_days: int,
) -> List[Tuple[str, int]]:
    """Return up to window_days rows of (date, count) strictly before before_date."""
    cutoff = (
        datetime.date.fromisoformat(before_date)
        - datetime.timedelta(days=window_days)
    ).isoformat()

    with _connect() as conn:
        rows = conn.execute("""
            SELECT date, count FROM ticker_mentions
            WHERE ticker = ?
              AND date >= ?
              AND date < ?
            ORDER BY date
        """, (ticker, cutoff, before_date)).fetchall()

    return [(r["date"], r["count"]) for r in rows]


def get_today_counts(date: str) -> Dict[str, int]:
    """Return all ticker mention counts for a specific date."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT ticker, count FROM ticker_mentions
            WHERE date = ?
        """, (date,)).fetchall()
    return {r["ticker"]: r["count"] for r in rows}


def get_all_tickers_with_history(before_date: str, min_days: int) -> List[str]:
    """Return tickers that have at least min_days of history before before_date."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT ticker FROM ticker_mentions
            WHERE date < ?
            GROUP BY ticker
            HAVING COUNT(*) >= ?
        """, (before_date, min_days)).fetchall()
    return [r["ticker"] for r in rows]

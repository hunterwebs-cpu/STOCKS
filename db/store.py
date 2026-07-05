"""SQLite persistence for daily ticker mention counts.

Schema:
    mentions(date, ticker, source, count)  — one row per ticker per source per day
    run_days(date)                         — every date the scraper actually ran

Baselines are computed over *run days* only, so days the job didn't run
don't get treated as zero-mention days and drag the mean down.
"""

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mentions (
    date   TEXT    NOT NULL,
    ticker TEXT    NOT NULL,
    source TEXT    NOT NULL,
    count  INTEGER NOT NULL,
    PRIMARY KEY (date, ticker, source)
);
CREATE INDEX IF NOT EXISTS idx_mentions_ticker ON mentions (ticker, date);

CREATE TABLE IF NOT EXISTS run_days (
    date TEXT PRIMARY KEY
);
"""


class MentionStore:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def upsert_mentions(self, date: str, source: str, counts: dict[str, int]):
        """Record today's counts for one source. Re-running the same night
        replaces that source's rows rather than double-counting."""
        self.conn.executemany(
            """
            INSERT INTO mentions (date, ticker, source, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (date, ticker, source)
            DO UPDATE SET count = excluded.count
            """,
            [(date, ticker, source, count) for ticker, count in counts.items()],
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO run_days (date) VALUES (?)", (date,)
        )
        self.conn.commit()

    def totals_for_date(self, date: str) -> dict[str, int]:
        """Total mentions per ticker (all sources summed) on one date."""
        rows = self.conn.execute(
            "SELECT ticker, SUM(count) FROM mentions WHERE date = ? GROUP BY ticker",
            (date,),
        )
        return dict(rows.fetchall())

    def baseline_dates(self, before_date: str, window: int) -> list[str]:
        """The most recent `window` run days strictly before `before_date`."""
        rows = self.conn.execute(
            "SELECT date FROM run_days WHERE date < ? ORDER BY date DESC LIMIT ?",
            (before_date, window),
        )
        return [r[0] for r in rows.fetchall()]

    def history(self, ticker: str, dates: list[str]) -> list[int]:
        """Daily totals for a ticker over the given dates, zero-filled for
        run days on which the ticker wasn't mentioned at all."""
        if not dates:
            return []
        placeholders = ",".join("?" * len(dates))
        rows = self.conn.execute(
            f"""
            SELECT date, SUM(count) FROM mentions
            WHERE ticker = ? AND date IN ({placeholders})
            GROUP BY date
            """,
            [ticker, *dates],
        )
        by_date = dict(rows.fetchall())
        return [by_date.get(d, 0) for d in dates]

    def first_seen(self, ticker: str) -> str | None:
        row = self.conn.execute(
            "SELECT MIN(date) FROM mentions WHERE ticker = ?", (ticker,)
        ).fetchone()
        return row[0] if row else None

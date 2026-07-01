from dataclasses import dataclass
from typing import List, Optional

from analyzer.buzz_detector import BuzzSignal
from analyzer.technical import TechnicalData


@dataclass
class ReportRow:
    ticker: str
    z_score: float
    today_mentions: int
    baseline_mean: float
    rsi: Optional[float]
    rsi_zone: str
    signal_label: str


def build_report(
    date: str,
    signals: List[BuzzSignal],
    technical_map: dict,
) -> str:
    rows: List[ReportRow] = []
    for sig in signals:
        tech: TechnicalData = technical_map.get(sig.ticker)
        rows.append(ReportRow(
            ticker=sig.ticker,
            z_score=sig.z_score,
            today_mentions=sig.today_mentions,
            baseline_mean=sig.baseline_mean,
            rsi=tech.rsi if tech else None,
            rsi_zone=tech.rsi_zone if tech else "UNKNOWN",
            signal_label=tech.signal_label if tech else "BUZZ — RSI unavailable",
        ))

    header = (
        f"NIGHTLY BUZZ REPORT — {date}\n"
        f"{'=' * 60}\n"
        f"Stocks with social mention spike >= 1.2σ above 30-day baseline\n"
        f"Total flagged: {len(rows)}\n"
    )

    if not rows:
        return header + "\nNo tickers met the buzz threshold today.\n"

    col_ticker   = 8
    col_zscore   = 10
    col_mentions = 10
    col_avg      = 10
    col_rsi      = 10
    col_zone     = 12
    col_signal   = 40

    col_header = (
        f"\n{'TICKER':<{col_ticker}} "
        f"{'Z-SCORE':<{col_zscore}} "
        f"{'MENTIONS':<{col_mentions}} "
        f"{'30D AVG':<{col_avg}} "
        f"{'RSI(21)':<{col_rsi}} "
        f"{'RSI ZONE':<{col_zone}} "
        f"{'SIGNAL':<{col_signal}}\n"
        f"{'-' * 72}\n"
    )

    body = ""
    for row in rows:
        rsi_str = f"{row.rsi:.1f}" if row.rsi is not None else "N/A"
        body += (
            f"{row.ticker:<{col_ticker}} "
            f"{row.z_score:<{col_zscore}.2f} "
            f"{row.today_mentions:<{col_mentions}} "
            f"{row.baseline_mean:<{col_avg}.1f} "
            f"{rsi_str:<{col_rsi}} "
            f"{row.rsi_zone:<{col_zone}} "
            f"{row.signal_label:<{col_signal}}\n"
        )

    footer = (
        f"\nSources: Reddit (WSB, r/stocks, r/investing, r/options, "
        f"r/pennystocks, r/stockmarket), StockTwits\n"
        f"RSI: 21-period daily | Baseline: 30-day rolling mean/std\n"
    )

    return header + col_header + body + footer

"""Builds the plain-text nightly buzz report."""

import config

_HEADER = (
    f"{'TICKER':<8} {'Z-SCORE':<10} {'MENTIONS':<10} {'30D AVG':<10} "
    f"{'RSI(21)':<10} {'RSI ZONE':<12} SIGNAL"
)
_RULE_WIDE = "=" * 60
_RULE_TABLE = "-" * 72


def build_report(date: str, rows: list[dict]) -> str:
    """`rows` items: ticker, z_score, mentions, baseline_avg, rsi, rsi_zone, signal."""
    lines = [
        f"NIGHTLY BUZZ REPORT — {date}",
        _RULE_WIDE,
        f"Stocks with social mention spike >= {config.Z_SCORE_THRESHOLD}σ "
        f"above {config.BASELINE_DAYS}-day baseline",
        f"Total flagged: {len(rows)}",
        "",
        _HEADER,
        _RULE_TABLE,
    ]

    if rows:
        for r in rows:
            rsi_str = f"{r['rsi']:.1f}" if r["rsi"] is not None else "N/A"
            lines.append(
                f"{r['ticker']:<8} {r['z_score']:<10.2f} {r['mentions']:<10} "
                f"{r['baseline_avg']:<10.1f} {rsi_str:<10} {r['rsi_zone']:<12} "
                f"{r['signal']}"
            )
    else:
        lines.append("(no tickers flagged tonight)")

    lines += [
        "",
        "Sources: Reddit mentions (WSB, r/stocks, r/investing, r/options, "
        "r/pennystocks, r/stockmarket — direct API and/or ApeWisdom aggregate), "
        "StockTwits",
        f"RSI: {config.RSI_PERIOD}-period daily | "
        f"Baseline: {config.BASELINE_DAYS}-day rolling mean/std",
    ]
    return "\n".join(lines) + "\n"

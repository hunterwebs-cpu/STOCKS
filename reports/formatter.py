"""Builds the plain-text nightly buzz report."""

import config

_HEADER = (
    f"{'TICKER':<8} {'Z-SCORE':<9} {'MENTIONS':<9} {'30D AVG':<9} "
    f"{'RSI(21)':<8} {'ZONE':<11} {'SHORT%':<8} {'DTC':<6} SIGNAL"
)
_RULE_WIDE = "=" * 60
_RULE_TABLE = "-" * 100


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
            sf = r.get("short_float")
            sf_str = f"{sf:.1f}%" if sf is not None else "n/a"
            dtc = r.get("days_to_cover")
            dtc_str = f"{dtc:.1f}" if dtc is not None else "n/a"
            signal = r["signal"]
            if r.get("squeeze"):
                signal = f"SQUEEZE WATCH | {signal}"
            lines.append(
                f"{r['ticker']:<8} {r['z_score']:<9.2f} {r['mentions']:<9} "
                f"{r['baseline_avg']:<9.1f} {rsi_str:<8} {r['rsi_zone']:<11} "
                f"{sf_str:<8} {dtc_str:<6} {signal}"
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
        f"SHORT%: short float (Finviz, lags up to ~2wk) | DTC: days to cover | "
        f"SQUEEZE WATCH: short float >= {config.SQUEEZE_SHORT_FLOAT_PCT:.0f}% "
        f"(or >= {config.SQUEEZE_ALT_SHORT_FLOAT_PCT:.0f}% with DTC >= "
        f"{config.SQUEEZE_ALT_DTC:.0f})",
    ]
    return "\n".join(lines) + "\n"

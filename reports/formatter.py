"""Builds the plain-text nightly buzz report."""

import config

_HEADER = (
    f"{'TICKER':<8} {'Z-SCORE':<9} {'MENTIONS':<9} {'30D AVG':<9} "
    f"{'RSI(21)':<8} {'ZONE':<11} {'SHORT%':<8} {'DTC':<6} SIGNAL"
)
_MOVERS_HEADER = (
    f"{'TICKER':<8} {'MENTIONS':<9} {'BASELINE':<9} {'CHANGE':<9} {'Z-SCORE':<9} FLAGGED?"
)
_RULE_WIDE = "=" * 60
_RULE_TABLE = "-" * 100
_RULE_MOVERS = "-" * 60

_KEY_LINES = [
    "KEY — HOW TO READ THIS REPORT",
    _RULE_WIDE,
    "Z-SCORE       How unusual today's mention count is vs. this ticker's own",
    "              recent history, in standard deviations. 1.2+ is unusual,",
    "              3+ is rare.",
    "RSI(21)       Price momentum, 0-100. Below 30 = oversold (may be due for",
    "              a bounce). Above 70 = overbought (may be due to pull back).",
    "SHORT%        Percent of a company's tradeable shares currently sold",
    "              short (bets the price will fall). Higher = more fuel for",
    "              a squeeze if the price rises and shorts must buy back.",
    "DTC           Days-to-cover: how many days of average volume it would",
    "              take short-sellers to buy back all their borrowed shares.",
    "              Higher = harder for shorts to exit quickly.",
    "SHORT TREND   Whether daily short-selling (FINRA data) is rising (^) or",
    "              falling (v). Rising = shorts still piling in. Falling =",
    "              shorts may be covering — itself a source of upward",
    "              price pressure.",
    "SQUEEZE WATCH Heavy social buzz + a high short float at the same time —",
    "              the classic setup for a short squeeze: rising prices force",
    "              short-sellers to buy back stock, which pushes the price",
    "              higher still, forcing more covering, and so on.",
]


def _movers_table(movers: list[dict]) -> list[str]:
    lines = [
        "",
        _RULE_WIDE,
        f"TOP {config.TOP_MOVERS_COUNT} MOVERS — biggest deviation from each ticker's own baseline "
        "today (broader than the flagged list above)",
        _RULE_MOVERS,
        _MOVERS_HEADER,
        _RULE_MOVERS,
    ]
    if not movers:
        lines.append("(not enough baseline history yet to rank movers)")
        return lines
    for m in movers:
        pct = m.get("pct_change")
        pct_str = f"{pct:+.0f}%" if pct is not None else "n/a"
        flagged_str = "yes" if m.get("flagged") else ""
        lines.append(
            f"{m['ticker']:<8} {m['mentions']:<9} {m['baseline_avg']:<9.1f} "
            f"{pct_str:<9} {m['z_score']:<9.2f} {flagged_str}"
        )
    return lines


def build_report(date: str, rows: list[dict], movers: list[dict] | None = None) -> str:
    """`rows` items: ticker, z_score, mentions, baseline_avg, rsi, rsi_zone,
    signal, short_float, days_to_cover, sv_trend, squeeze.
    `movers` items: ticker, mentions, baseline_avg, z_score, pct_change, flagged.
    """
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

    lines += _movers_table(movers or [])

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
        "",
    ]
    lines += _KEY_LINES
    return "\n".join(lines) + "\n"

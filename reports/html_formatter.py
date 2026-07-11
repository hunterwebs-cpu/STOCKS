"""Styled HTML version of the nightly buzz report.

Email-client-safe: table-based layout, all styles inline, with a small
<style> block only for dark-mode overrides (honored by browsers and the
clients that support prefers-color-scheme; harmless elsewhere). The same
document is used as the email HTML body and as the attached .html file.
"""

import html

import config

# Zone chips ride the diverging blue<->red scale (oversold = cool, overbought
# = hot) with a neutral gray midpoint. Every chip carries its text label, so
# color never has to work alone.
ZONE_CHIP = {
    "OVERSOLD":   {"bg": "#cde2fb", "fg": "#104281"},
    "WEAK":       {"bg": "#e0ecfb", "fg": "#1c5cab"},
    "NEUTRAL":    {"bg": "#f0efec", "fg": "#52514e"},
    "STRONG":     {"bg": "#fbe3d8", "fg": "#9c3f14"},
    "OVERBOUGHT": {"bg": "#f8dcdc", "fg": "#a32d2d"},
    "N/A":        {"bg": "#f0efec", "fg": "#898781"},
}

_FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
_MONO_NUM = "font-variant-numeric: tabular-nums;"


def _chip(zone: str) -> str:
    c = ZONE_CHIP.get(zone, ZONE_CHIP["N/A"])
    return (
        f'<span style="display:inline-block; padding:3px 10px; border-radius:999px; '
        f'background:{c["bg"]}; color:{c["fg"]}; font-size:12px; font-weight:600; '
        f'letter-spacing:0.4px; white-space:nowrap;">{html.escape(zone)}</span>'
    )


def _signal_note(signal: str) -> str:
    """The human tail of 'BUZZ + ZONE — note' (the chip already shows the zone)."""
    return signal.split("—", 1)[1].strip() if "—" in signal else signal


def _squeeze_chip() -> str:
    return (
        '<span style="display:inline-block; padding:3px 10px; border-radius:999px; '
        'background:#d03b3b; color:#ffffff; font-size:11px; font-weight:700; '
        'letter-spacing:0.5px; white-space:nowrap;">&#128293; SQUEEZE WATCH</span>'
    )


def _short_cell(r: dict) -> str:
    sf = r.get("short_float")
    if sf is None:
        return '<span style="color:#898781;">&mdash;</span>'
    trend = r.get("sv_trend")
    arrow = ""
    if trend is not None and trend >= 0.02:
        arrow = ' <span style="color:#a32d2d; font-size:11px;" title="short volume rising">&#9650;</span>'
    elif trend is not None and trend <= -0.02:
        arrow = ' <span style="color:#0ca30c; font-size:11px;" title="short volume falling — covering?">&#9660;</span>'
    return f'<span class="ink" style="color:#0b0b0b;">{sf:.1f}%</span>{arrow}'


def _kpi(label: str, value: str, sub: str = "") -> str:
    sub_html = (
        f'<div style="font-size:12px; color:#898781; padding-top:2px;">{sub}</div>'
        if sub
        else ""
    )
    return f"""
      <td class="card" width="33%" style="background:#fcfcfb; border:1px solid #e1e0d9; border-radius:10px; padding:14px 16px;">
        <div style="font-size:11px; font-weight:600; letter-spacing:1px; color:#898781; text-transform:uppercase;">{label}</div>
        <div class="ink" style="font-size:26px; font-weight:650; color:#0b0b0b; padding-top:4px;">{value}</div>
        {sub_html}
      </td>"""


def _row(r: dict, last: bool) -> str:
    rsi_str = f"{r['rsi']:.1f}" if r["rsi"] is not None else "—"
    dtc = r.get("days_to_cover")
    dtc_str = f"{dtc:.1f}" if dtc is not None else "&mdash;"
    border = "" if last else "border-bottom:1px solid #e1e0d9;"
    signal_html = html.escape(_signal_note(r["signal"]))
    if r.get("squeeze"):
        signal_html = f'{_squeeze_chip()}<br><span style="font-size:12px;">{signal_html}</span>'
    return f"""
          <tr>
            <td class="ink" style="padding:12px 10px; {border} font-size:15px; font-weight:700; color:#0b0b0b;">{html.escape(r['ticker'])}</td>
            <td class="ink" style="padding:12px 10px; {border} font-size:14px; font-weight:650; color:#0b0b0b; {_MONO_NUM} text-align:right;">{r['z_score']:.2f}&sigma;</td>
            <td style="padding:12px 10px; {border} {_MONO_NUM} text-align:right; white-space:nowrap;">
              <span class="ink" style="font-size:14px; color:#0b0b0b;">{r['mentions']}</span>
              <span style="font-size:12px; color:#898781;">&nbsp;vs {r['baseline_avg']:.1f} avg</span>
            </td>
            <td class="ink" style="padding:12px 10px; {border} font-size:14px; color:#0b0b0b; {_MONO_NUM} text-align:right;">{rsi_str}</td>
            <td style="padding:12px 10px; {border} text-align:center;">{_chip(r['rsi_zone'])}</td>
            <td style="padding:12px 10px; {border} font-size:14px; {_MONO_NUM} text-align:right; white-space:nowrap;">{_short_cell(r)}</td>
            <td class="ink" style="padding:12px 10px; {border} font-size:14px; color:#0b0b0b; {_MONO_NUM} text-align:right;">{dtc_str}</td>
            <td class="sub" style="padding:12px 10px; {border} font-size:13px; color:#52514e;">{signal_html}</td>
          </tr>"""


def _table(rows: list[dict]) -> str:
    if not rows:
        return """
        <div style="padding:36px 20px; text-align:center;">
          <div class="ink" style="font-size:15px; font-weight:600; color:#0b0b0b;">No tickers flagged tonight</div>
          <div class="sub" style="font-size:13px; color:#52514e; padding-top:6px;">
            Nothing crossed the buzz threshold &mdash; the baseline keeps building either way.
          </div>
        </div>"""

    header_cells = "".join(
        f'<td style="padding:10px 14px; font-size:11px; font-weight:600; '
        f'letter-spacing:1px; color:#898781; text-transform:uppercase; '
        f'border-bottom:1px solid #c3c2b7; text-align:{align}; white-space:nowrap;">{name}</td>'
        for name, align in [
            ("Ticker", "left"), ("Z-score", "right"), ("Mentions", "right"),
            (f"RSI({config.RSI_PERIOD})", "right"), ("Zone", "center"),
            ("Short flt", "right"), ("DTC", "right"), ("Signal", "left"),
        ]
    )
    body = "".join(_row(r, i == len(rows) - 1) for i, r in enumerate(rows))
    return f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
          <tr>{header_cells}</tr>
          {body}
        </table>"""


def _mover_row(m: dict, last: bool) -> str:
    border = "" if last else "border-bottom:1px solid #e1e0d9;"
    pct = m.get("pct_change")
    pct_str = f"{pct:+.0f}%" if pct is not None else "&mdash;"
    flag_html = (
        '<span style="color:#a32d2d; font-weight:600;">&#9733; flagged</span>'
        if m.get("flagged") else '<span style="color:#c3c2b7;">&mdash;</span>'
    )
    return f"""
          <tr>
            <td class="ink" style="padding:10px 10px; {border} font-size:14px; font-weight:700; color:#0b0b0b;">{html.escape(m['ticker'])}</td>
            <td class="ink" style="padding:10px 10px; {border} font-size:13px; color:#0b0b0b; {_MONO_NUM} text-align:right;">{m['mentions']}</td>
            <td class="sub" style="padding:10px 10px; {border} font-size:13px; color:#52514e; {_MONO_NUM} text-align:right;">{m['baseline_avg']:.1f}</td>
            <td class="ink" style="padding:10px 10px; {border} font-size:13px; font-weight:600; color:#0b0b0b; {_MONO_NUM} text-align:right;">{pct_str}</td>
            <td class="ink" style="padding:10px 10px; {border} font-size:13px; color:#0b0b0b; {_MONO_NUM} text-align:right;">{m['z_score']:.2f}&sigma;</td>
            <td style="padding:10px 10px; {border} font-size:12px; text-align:right;">{flag_html}</td>
          </tr>"""


def _movers_table(movers: list[dict]) -> str:
    if not movers:
        return """
        <div style="padding:24px 20px; text-align:center;">
          <div class="sub" style="font-size:13px; color:#52514e;">
            Not enough baseline history yet to rank movers &mdash; check back tomorrow.
          </div>
        </div>"""
    header_cells = "".join(
        f'<td style="padding:8px 10px; font-size:10px; font-weight:600; '
        f'letter-spacing:0.6px; color:#898781; text-transform:uppercase; '
        f'border-bottom:1px solid #c3c2b7; text-align:{align}; white-space:nowrap;">{name}</td>'
        for name, align in [
            ("Ticker", "left"), ("Mentions", "right"), ("Baseline avg", "right"),
            ("Change", "right"), ("Z-score", "right"), ("", "right"),
        ]
    )
    body = "".join(_mover_row(m, i == len(movers) - 1) for i, m in enumerate(movers))
    return f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
          <tr>{header_cells}</tr>
          {body}
        </table>"""


_KEY_ROWS = [
    ("Z-SCORE", "How unusual today's mention count is vs. this ticker's own recent history, in standard deviations. 1.2+ is unusual, 3+ is rare."),
    (f"RSI({config.RSI_PERIOD})", "Price momentum, 0&ndash;100. Below 30 = oversold (may be due for a bounce). Above 70 = overbought (may be due to pull back)."),
    ("Short float %", "Percent of a company's tradeable shares currently sold short (bets the price will fall). Higher = more fuel for a squeeze if the price rises and shorts must buy back."),
    ("DTC", "Days-to-cover: how many days of average trading volume it would take short-sellers to buy back all their borrowed shares. Higher = harder for shorts to exit quickly."),
    ("Short trend &#9650;/&#9660;", "Whether daily short-selling activity (FINRA data) is rising or falling. Rising = shorts still piling in. Falling = shorts may be covering &mdash; itself a source of upward price pressure."),
    ("&#128293; Squeeze watch", "Heavy social buzz + a high short float at the same time &mdash; the classic setup for a short squeeze: rising prices force short-sellers to buy back stock, pushing the price higher still, forcing more covering."),
]


def _key_section() -> str:
    rows_html = "".join(
        f"""
        <tr>
          <td class="ink" style="padding:8px 12px 8px 0; font-size:12px; font-weight:700; color:#0b0b0b; white-space:nowrap; vertical-align:top;">{term}</td>
          <td class="sub" style="padding:8px 0; font-size:12px; color:#52514e; line-height:1.5;">{meaning}</td>
        </tr>"""
        for term, meaning in _KEY_ROWS
    )
    return f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          {rows_html}
        </table>"""


def build_html_report(date: str, rows: list[dict], movers: list[dict] | None = None) -> str:
    movers = movers or []
    top_z = f"{rows[0]['z_score']:.2f}&sigma;" if rows else "&mdash;"
    top_ticker = html.escape(rows[0]["ticker"]) if rows else ""
    n_squeeze = sum(1 for r in rows if r.get("squeeze"))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Nightly Buzz Report — {date}</title>
<style>
  @media (prefers-color-scheme: dark) {{
    .bg-page  {{ background:#0d0d0d !important; }}
    .card     {{ background:#1a1a19 !important; border-color:#2c2c2a !important; }}
    .ink      {{ color:#ffffff !important; }}
    .sub      {{ color:#c3c2b7 !important; }}
  }}
</style>
</head>
<body class="bg-page" style="margin:0; padding:0; background:#f9f9f7; font-family:{_FONT};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="bg-page" style="background:#f9f9f7;">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px; width:100%;">

        <!-- Header -->
        <tr>
          <td style="padding:0 4px 18px;">
            <div style="font-size:11px; font-weight:600; letter-spacing:2px; color:#898781; text-transform:uppercase;">Nightly Buzz Report</div>
            <div class="ink" style="font-size:28px; font-weight:700; color:#0b0b0b; padding-top:4px;">{date}</div>
            <div class="sub" style="font-size:13px; color:#52514e; padding-top:6px;">
              Stocks whose social-media mentions spiked &ge; {config.Z_SCORE_THRESHOLD}&sigma; above their own {config.BASELINE_DAYS}-day baseline
            </div>
          </td>
        </tr>

        <!-- KPI row -->
        <tr>
          <td style="padding-bottom:16px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                {_kpi("Flagged tonight", str(len(rows)))}
                <td width="12" style="font-size:0;">&nbsp;</td>
                {_kpi("Top spike", top_z, top_ticker)}
                <td width="12" style="font-size:0;">&nbsp;</td>
                {_kpi("Squeeze watch", str(n_squeeze), f"short float &ge; {config.SQUEEZE_SHORT_FLOAT_PCT:.0f}%")}
              </tr>
            </table>
          </td>
        </tr>

        <!-- Results table -->
        <tr>
          <td class="card" style="background:#fcfcfb; border:1px solid #e1e0d9; border-radius:10px; padding:6px 6px 2px;">
            {_table(rows)}
          </td>
        </tr>

        <!-- Top movers -->
        <tr>
          <td style="padding:22px 4px 8px;">
            <div class="ink" style="font-size:15px; font-weight:700; color:#0b0b0b;">Top {config.TOP_MOVERS_COUNT} Movers</div>
            <div class="sub" style="font-size:12px; color:#52514e; padding-top:2px;">
              Biggest deviation from each ticker's own baseline today &mdash; broader than the flagged list above, so there's always something to watch.
            </div>
          </td>
        </tr>
        <tr>
          <td class="card" style="background:#fcfcfb; border:1px solid #e1e0d9; border-radius:10px; padding:6px 6px 2px;">
            {_movers_table(movers)}
          </td>
        </tr>

        <!-- Key / glossary -->
        <tr>
          <td style="padding:22px 4px 8px;">
            <div class="ink" style="font-size:15px; font-weight:700; color:#0b0b0b;">Key &mdash; How to Read This Report</div>
          </td>
        </tr>
        <tr>
          <td class="card" style="background:#fcfcfb; border:1px solid #e1e0d9; border-radius:10px; padding:14px 16px;">
            {_key_section()}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:18px 4px 0;">
            <div style="font-size:12px; color:#898781; line-height:1.6;">
              Sources: Reddit mentions (r/wallstreetbets, r/stocks, r/investing, r/options, r/pennystocks, r/stockmarket &mdash; direct API and/or ApeWisdom aggregate) &middot; StockTwits<br>
              RSI: {config.RSI_PERIOD}-period daily via Yahoo Finance &middot; Baseline: {config.BASELINE_DAYS}-day rolling mean/std, today excluded &middot; Min {config.MIN_HISTORY_DAYS} days history<br>
              Zones: &lt;30 OVERSOLD &middot; 30&ndash;40 WEAK &middot; 40&ndash;60 NEUTRAL &middot; 60&ndash;70 STRONG &middot; &gt;70 OVERBOUGHT<br>
              Short flt: short float % of shares (Finviz; exchange data lags up to ~2 weeks) &middot; DTC: days to cover &middot; &#9650;/&#9660;: daily short-volume ratio rising/falling (FINRA) &middot; &#128293; SQUEEZE WATCH: short float &ge; {config.SQUEEZE_SHORT_FLOAT_PCT:.0f}% (or &ge; {config.SQUEEZE_ALT_SHORT_FLOAT_PCT:.0f}% with DTC &ge; {config.SQUEEZE_ALT_DTC:.0f})<br>
              Automated research signal &mdash; not investment advice.
            </div>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""

# STOCKS — Nightly Buzz Screener

Nightly automation that flags stocks showing **statistically significant spikes
in social media mentions** — not just high raw volume, but deviation from each
ticker's own baseline. TSLA buzzing at 500 mentions is noise; a small-cap going
from 8 to 60 is signal.

## How it works

1. **Scrape** — Reddit (r/wallstreetbets, r/stocks, r/investing, r/options,
   r/pennystocks, r/stockmarket) via PRAW, plus the StockTwits public API.
   `$TICKER` cashtags are extracted from post titles, bodies, and the top 50
   comments per post, with a blacklist for false positives (CEO, IPO, USD, …).
2. **Store** — daily mention counts per ticker land in SQLite (`db/mentions.sqlite3`).
3. **Detect** — once a rolling baseline builds up, each ticker gets a z-score:
   `z = (today_mentions − 30d_mean) / 30d_std` (baseline excludes today).
   Anything at `z ≥ 1.2` (configurable) is flagged. A ticker needs at least
   5 prior days of history before it can be flagged.
4. **Confirm** — flagged tickers get RSI(21) on the daily timeframe via
   yfinance (free, no API key) and a combined signal:
   `BUZZ + OVERSOLD`, `BUZZ + NEUTRAL`, `BUZZ + OVERBOUGHT`, etc.
5. **Report** — plain-text table saved to `reports/output/` and emailed via SMTP.

### Sample report

```
NIGHTLY BUZZ REPORT — 2026-07-01
============================================================
Stocks with social mention spike >= 1.2σ above 30-day baseline
Total flagged: 2

TICKER   Z-SCORE    MENTIONS   30D AVG    RSI(21)    RSI ZONE     SIGNAL
------------------------------------------------------------------------
MSTR     3.21       184        41.2       34.1       WEAK         BUZZ + WEAK — Early interest, still soft
HOOD     1.87       62         18.4       58.3       NEUTRAL      BUZZ + NEUTRAL — Building momentum

Sources: Reddit (WSB, r/stocks, r/investing, r/options, r/pennystocks, r/stockmarket), StockTwits
RSI: 21-period daily | Baseline: 30-day rolling mean/std
```

RSI zones: `<30` OVERSOLD · `30–40` WEAK · `40–60` NEUTRAL · `60–70` STRONG · `>70` OVERBOUGHT

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in Reddit API + SMTP credentials
```

Reddit credentials: create a "script" app at <https://www.reddit.com/prefs/apps>.
StockTwits and yfinance need no keys.

## Run

```bash
python run_nightly.py
```

The first ~5 runs only build baseline history; flagging starts once a ticker
has enough prior days (`MIN_HISTORY_DAYS`, default 5) and improves as the
window fills to 30 days.

## Cron (nightly, ~8pm ET on trading-day eves Mon–Thu)

```cron
CRON_TZ=America/New_York
0 20 * * 1-4 cd /path/to/STOCKS && .venv/bin/python run_nightly.py >> cron.log 2>&1
```

(Sunday night is skipped by default since Monday-eve buzz accumulates over the
weekend; add `0` to the day-of-week list if you want it.)

## Project structure

```
STOCKS/
├── run_nightly.py             # main orchestrator
├── config.py                  # loads from .env
├── .env.example
├── requirements.txt
├── db/
│   └── store.py               # SQLite: upsert mentions, query history
├── scrapers/
│   ├── reddit_scraper.py      # PRAW, extracts $TICKER cashtags
│   └── stocktwits_scraper.py  # public API, trending + per-symbol
├── analyzer/
│   ├── buzz_detector.py       # z-score engine, flags >= 1.2σ
│   └── technical.py           # RSI(21) via yfinance
└── reports/
    ├── formatter.py           # builds the text report table
    └── emailer.py             # SMTP send
```

## Configuration

All knobs live in `.env` (see `.env.example`): z-score threshold, baseline
window, minimum history days, RSI period, subreddit list, post/comment limits,
StockTwits pacing, DB/report paths, and SMTP settings.

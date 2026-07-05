# STOCKS — Nightly Buzz Screener

Nightly automation that flags stocks showing **statistically significant spikes
in social media mentions** — not just high raw volume, but deviation from each
ticker's own baseline. TSLA buzzing at 500 mentions is noise; a small-cap going
from 8 to 60 is signal.

## How it works

1. **Scrape** — three sources, best-effort (any subset can fail without
   killing the run):
   - **ApeWisdom** (keyless): aggregated Reddit ticker mentions across the
     major investing subreddits — works with zero credentials, and is the
     Reddit signal while direct API access is pending.
   - **Reddit direct** via PRAW (r/wallstreetbets, r/stocks, r/investing,
     r/options, r/pennystocks, r/stockmarket): `$TICKER` cashtags from post
     titles, bodies, and top 50 comments per post, with a false-positive
     blacklist (CEO, IPO, USD, …). Runs only when `REDDIT_CLIENT_ID`/`SECRET`
     are set — note Reddit now gates API app creation behind its
     [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy)
     registration/approval.
   - **StockTwits** public API (keyless): trending symbols + per-symbol
     message streams.
2. **Store** — daily mention counts per ticker land in SQLite (`db/mentions.sqlite3`).
3. **Detect** — once a rolling baseline builds up, each ticker gets a z-score:
   `z = (today_mentions − 30d_mean) / 30d_std` (baseline excludes today).
   Anything at `z ≥ 1.2` (configurable) is flagged. A ticker needs at least
   5 prior days of history before it can be flagged.
4. **Confirm** — flagged tickers get RSI(21) on the daily timeframe via
   yfinance (free, no API key) and a combined signal:
   `BUZZ + OVERSOLD`, `BUZZ + NEUTRAL`, `BUZZ + OVERBOUGHT`, etc.
5. **Report** — saved to `reports/output/` as both `.txt` and a styled `.html`
   page, then emailed via SMTP to every address in `EMAIL_TO` (comma-separated).
   The email carries a plain-text fallback, the styled HTML as the message body,
   and the same HTML attached as a file recipients can open in a browser.

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

ApeWisdom, StockTwits, and yfinance need no keys — the screener is fully
functional without any credentials except SMTP for email delivery.

Reddit direct access (optional, adds depth): Reddit requires developer
registration and approval before an app can be created ("I'm a Developer" →
"I want to register to use the Reddit API" via the
[Developer Platform & Accessing Reddit Data](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data)
page). Once approved, create a "script" app at <https://www.reddit.com/prefs/apps>
and set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`.
Adding a new source mid-stream shifts total mention levels, so expect z-scores
to run a bit hot for a few days while the baseline adapts.

## Run

```bash
python run_nightly.py
```

The first ~5 runs only build baseline history; flagging starts once a ticker
has enough prior days (`MIN_HISTORY_DAYS`, default 5) and improves as the
window fills to 30 days.

## Scheduling

### Option A — Claude Code Routine (managed, no server needed)

A Routine (scheduled trigger) in Claude Code on the web fires a fresh cloud
session on a cron schedule. Each session clones this repo, checks out the
working branch, runs `run_nightly.py`, then commits the updated
`db/mentions.sqlite3` and `reports/output/` back — that commit IS the
persistence layer, since Routine containers are ephemeral.

Requirements:
- Credentials (`REDDIT_*`, `SMTP_*`, `EMAIL_*`) must be set as **environment
  variables on the Claude Code environment** (claude.ai → Claude Code →
  Environments → your environment → Environment variables). `config.py` reads
  plain environment variables, so no `.env` file is needed in the cloud.
- The environment's network policy must allow reddit.com, stocktwits.com,
  Yahoo Finance, and your SMTP host.

Docs: <https://code.claude.com/docs/en/claude-code-on-the-web>

### Option B — classic cron on your own machine

```cron
CRON_TZ=America/New_York
0 20 * * * cd /path/to/STOCKS && .venv/bin/python run_nightly.py >> cron.log 2>&1
```

Use `1-4` as the day-of-week field to restrict to trading-day eves (Mon–Thu).

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
│   ├── reddit_scraper.py      # PRAW, extracts $TICKER cashtags (needs API approval)
│   ├── apewisdom_scraper.py   # keyless Reddit-mentions aggregate
│   └── stocktwits_scraper.py  # public API, trending + per-symbol
├── analyzer/
│   ├── buzz_detector.py       # z-score engine, flags >= 1.2σ
│   └── technical.py           # RSI(21) via yfinance
└── reports/
    ├── formatter.py           # builds the text report table
    ├── html_formatter.py      # styled HTML report (email body + attachment)
    └── emailer.py             # SMTP multipart send (text + HTML + .html file)
```

## Configuration

All knobs live in `.env` (see `.env.example`): z-score threshold, baseline
window, minimum history days, RSI period, subreddit list, post/comment limits,
StockTwits pacing, DB/report paths, and SMTP settings.

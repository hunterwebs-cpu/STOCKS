"""Central configuration, loaded from .env (see .env.example)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, "")
    return value if value.strip() else default


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in _env(name, default).split(",") if item.strip()]


# ── Reddit ────────────────────────────────────────────────────────────────────
REDDIT_CLIENT_ID = _env("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = _env("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = _env("REDDIT_USER_AGENT", "buzz-screener/1.0")
SUBREDDITS = _env_list(
    "SUBREDDITS",
    "wallstreetbets,stocks,investing,options,pennystocks,stockmarket",
)
REDDIT_POST_LIMIT = int(_env("REDDIT_POST_LIMIT", "100"))
REDDIT_COMMENTS_PER_POST = int(_env("REDDIT_COMMENTS_PER_POST", "50"))

# ── StockTwits ────────────────────────────────────────────────────────────────
STOCKTWITS_SLEEP = float(_env("STOCKTWITS_SLEEP", "0.5"))
STOCKTWITS_RATE_LIMIT_BACKOFF = float(_env("STOCKTWITS_RATE_LIMIT_BACKOFF", "60"))

# ── Buzz detection ────────────────────────────────────────────────────────────
Z_SCORE_THRESHOLD = float(_env("Z_SCORE_THRESHOLD", "1.2"))
BASELINE_DAYS = int(_env("BASELINE_DAYS", "30"))
MIN_HISTORY_DAYS = int(_env("MIN_HISTORY_DAYS", "5"))

# ── Technicals ────────────────────────────────────────────────────────────────
RSI_PERIOD = int(_env("RSI_PERIOD", "21"))

# ── Storage ───────────────────────────────────────────────────────────────────
DB_PATH = _env("DB_PATH", str(BASE_DIR / "db" / "mentions.sqlite3"))
REPORT_DIR = _env("REPORT_DIR", str(BASE_DIR / "reports" / "output"))

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_ENABLED = _env("EMAIL_ENABLED", "true").lower() in ("1", "true", "yes")
SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = int(_env("SMTP_PORT", "587"))
SMTP_USER = _env("SMTP_USER")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
EMAIL_FROM = _env("EMAIL_FROM", SMTP_USER)
EMAIL_TO = _env_list("EMAIL_TO", "")

# ── Ticker extraction ─────────────────────────────────────────────────────────
# Common all-caps words that match the $TICKER pattern but aren't tickers.
TICKER_BLACKLIST = {
    "I", "A", "IT", "ME", "GO", "US", "UK", "CEO", "IPO", "ETF", "FDA",
    "SEC", "GDP", "USD", "EUR", "WHO", "IRS", "AM", "PM", "CFO", "IMF",
}

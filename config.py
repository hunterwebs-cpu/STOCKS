import os
from dotenv import load_dotenv

load_dotenv()

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "NightlyBuzzScreener/1.0")

REDDIT_SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "options",
    "pennystocks",
    "stockmarket",
]

BUZZ_Z_THRESHOLD = float(os.getenv("BUZZ_Z_THRESHOLD", "1.2"))
MIN_HISTORY_DAYS = int(os.getenv("MIN_HISTORY_DAYS", "5"))
BASELINE_WINDOW_DAYS = int(os.getenv("BASELINE_WINDOW_DAYS", "30"))

DB_PATH = os.getenv("DB_PATH", "buzz_mentions.db")
REPORT_DIR = os.getenv("REPORT_DIR", "output_reports")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT", "Nightly Buzz Report")
EMAIL_DRY_RUN = os.getenv("EMAIL_DRY_RUN", "false").lower() == "true"

# Words that look like tickers but are not
TICKER_BLACKLIST = {
    "I", "A", "IT", "ME", "GO", "US", "UK", "CEO", "IPO", "ETF",
    "FDA", "SEC", "GDP", "USD", "EUR", "WHO", "IRS", "AM", "PM",
    "CFO", "IMF", "AI", "AT", "BE", "BY", "DO", "IF", "IN", "IS",
    "NO", "OF", "ON", "OR", "SO", "TO", "UP", "AN", "AS", "AT",
    "BUT", "FOR", "NOT", "THE", "AND", "ARE", "WAS", "ALL", "CAN",
    "ATH", "DD", "TA", "OG", "EV", "AR", "PE", "PO",
}

RSI_PERIOD = 21
RSI_ZONE_OVERSOLD = 30
RSI_ZONE_WEAK = 40
RSI_ZONE_NEUTRAL = 60
RSI_ZONE_STRONG = 70

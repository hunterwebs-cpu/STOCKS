"""Market data sources. Both return regular-session 5-min bars (index = bar
start, America/New_York) containing only *completed* bars."""
import os

import pandas as pd

NY = "America/New_York"


def _completed(df: pd.DataFrame, now=None) -> pd.DataFrame:
    now = now or pd.Timestamp.now(tz=NY)
    return df[df.index + pd.Timedelta(minutes=5) <= now]


class YahooData:
    """Free, no keys. ~60 days of 5-min history; near-real-time intraday."""

    def bars5(self, symbol: str, days: int = 59) -> pd.DataFrame:
        import yfinance as yf
        d = yf.download(symbol, period=f"{days}d", interval="5m", progress=False, prepost=False)
        d.columns = d.columns.get_level_values(0)
        d = d[["Open", "High", "Low", "Close"]].dropna()
        d.index = d.index.tz_convert(NY)
        d = d.between_time("09:30", "15:55")
        return _completed(d)


class WebullData:
    """Webull OpenAPI via the official SDK (pip install webull-openapi-python-sdk).
    Needs WEBULL_APP_KEY / WEBULL_APP_SECRET in the environment.
    NOT YET VERIFIED against a live key: check the first run's output."""

    def __init__(self):
        from webull.core.client import ApiClient
        from webull.data.data_client import DataClient
        key, secret = os.environ.get("WEBULL_APP_KEY"), os.environ.get("WEBULL_APP_SECRET")
        if not key or not secret:
            raise RuntimeError("Set WEBULL_APP_KEY and WEBULL_APP_SECRET to use Webull data")
        self.client = DataClient(ApiClient(key, secret, os.environ.get("WEBULL_REGION_ID", "us")))

    def bars5(self, symbol: str, days: int = 20) -> pd.DataFrame:
        count = min(1200, days * 78)
        resp = self.client.market_data.get_history_bar(
            symbol=symbol, category="US_ETF", timespan="M5", count=str(count))
        rows = resp.json() if hasattr(resp, "json") else resp
        if isinstance(rows, dict):
            rows = rows.get("result") or rows.get("data") or rows
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert(NY)
        df = df.set_index("time").sort_index()
        df = df.rename(columns=str.capitalize)[["Open", "High", "Low", "Close"]].astype(float)
        return _completed(df.between_time("09:30", "15:55"))


def source(name: str):
    return WebullData() if name == "webull" else YahooData()

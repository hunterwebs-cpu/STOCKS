"""The user's setup, coded. Pure functions of completed bars only."""
import pandas as pd

from .indicators import setup_frame


def resample(df5: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Regular-session bars anchored at 09:30, labeled by bar *start*."""
    out = df5.resample(f"{minutes}min", origin="start_day", offset="30min").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return out


def build_signals(df5: pd.DataFrame, cfg) -> pd.DataFrame:
    """One row per completed 10-min bar (indexed by bar *end*) with:
    long_setup / short_setup: 10-min stack + momentum color just turned on,
    while the last completed 60-min bar shows the same stack + momentum."""
    b10 = resample(df5, 10)
    b60 = resample(df5, 60)
    s10 = setup_frame(b10, cfg.ema_lengths, cfg.squeeze_len, cfg.atr_len)
    s60 = setup_frame(b60, cfg.ema_lengths, cfg.squeeze_len, cfg.atr_len)

    # 60-min state known at each 10-min bar's close: last 60-min bar whose end <= that time
    s60_end = s60.copy()
    s60_end.index = s60.index + pd.Timedelta(minutes=60)
    b10_end = b10.index + pd.Timedelta(minutes=10)
    f = s60_end[["bull", "bear", "light_blue", "red"]].astype(float).reindex(
        s60_end.index.union(b10_end)).ffill().reindex(b10_end)
    f.index = b10.index

    long_now = s10.bull & s10.light_blue
    short_now = s10.bear & s10.red
    out = b10.copy()
    out["atr"] = s10.atr
    out["htf_long"] = (f.bull == 1) & (f.light_blue == 1)
    out["htf_short"] = (f.bear == 1) & (f.red == 1)
    out["long_setup"] = long_now & ~long_now.shift(1, fill_value=False) & out.htf_long
    out["short_setup"] = short_now & ~short_now.shift(1, fill_value=False) & out.htf_short
    out.index = b10_end          # rows become actionable at bar close
    out["bar_start"] = b10.index
    return out

"""TTM Squeeze on intraday bars (10-min and 60-min), SPY and QQQ.

Two views per variant:
  * Lab: after a fire, does price reach +TARGET ATR before -STOP ATR within
    HOLD bars, vs. the base rate for the same direction on every bar?
  * Trade: enter next bar's open in the momentum direction, exit after
    two bars of momentum fading (Carter's rule), at the session close for day
    trades, or at MAX_BARS. Results in R (multiples of 1 ATR at entry).

Data: Yahoo gives ~3 years of 60-min and only ~60 days of 5-min (resampled
to 10-min). Drop CSVs with Datetime,Open,High,Low,Close into data/ named
SPY_10m.csv / QQQ_60m.csv etc. to test on longer history (e.g. from Webull).

Run: python3 research/intraday_squeeze.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DATA = Path(__file__).resolve().parent.parent / "data"
TARGET, STOP, HOLD = 1.0, 2.0, 6
COST_R = 0.02            # round-trip cost in R units


def load(sym, tf):
    f = DATA / f"{sym}_{tf}.csv"
    if f.exists():
        return pd.read_csv(f, index_col=0, parse_dates=True)
    if tf == "60m":
        d = yf.download(sym, period="730d", interval="60m", progress=False)
    else:
        d = yf.download(sym, period="60d", interval="5m", progress=False)
    d.columns = d.columns.get_level_values(0)
    d = d[["Open", "High", "Low", "Close"]].dropna()
    d.index = d.index.tz_convert("America/New_York")
    if tf == "10m":
        d = d.resample("10min", origin="start_day", offset="30min").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return d


def squeeze(df, n=20, bb_k=2.0, kc_k=1.5):
    c, h, l = df.Close, df.High, df.Low
    sma, sd = c.rolling(n).mean(), c.rolling(n).std(ddof=0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    on = (bb_k * sd) < (kc_k * atr)
    delta = c - ((h.rolling(n).max() + l.rolling(n).min()) / 2 + sma) / 2
    x = np.arange(n)
    mom = delta.rolling(n).apply(lambda y: np.polyval(np.polyfit(x, y, 1), n - 1), raw=True)
    dots = on.groupby((~on).cumsum()).cumsum()       # consecutive squeeze bars
    fired = on.shift(1, fill_value=False) & ~on
    return pd.DataFrame({"on": on, "mom": mom, "atr": tr.rolling(14).mean(),
                         "dots_before": dots.shift(1), "fired": fired,
                         "e8": c.ewm(span=8, adjust=False).mean(),
                         "e21": c.ewm(span=21, adjust=False).mean(),
                         "e34": c.ewm(span=34, adjust=False).mean()})


def lab_outcomes(df, atr, direction):
    c, h, l, a = df.Close.values, df.High.values, df.Low.values, atr.values
    out = np.full(len(df), np.nan)
    for i in range(len(df) - HOLD):
        if np.isnan(a[i]):
            continue
        tgt, stp = c[i] + direction * TARGET * a[i], c[i] - direction * STOP * a[i]
        hit = 0
        for j in range(i + 1, i + HOLD + 1):
            if (l[j] <= stp) if direction > 0 else (h[j] >= stp):
                break
            if (h[j] >= tgt) if direction > 0 else (l[j] <= tgt):
                hit = 1
                break
        out[i] = hit
    return pd.Series(out, index=df.index)


def trades(df, sq, entries, direction, day_trade, max_bars):
    o, c, m, a = df.Open.values, df.Close.values, sq.mom.values, sq.atr.values
    day = df.index.normalize()
    last_of_day = np.r_[day[1:] != day[:-1], True]
    res, i, n = [], 0, len(df)
    ent = entries.values
    while i < n - 2:
        if not ent[i] or np.isnan(a[i]) or (day_trade and last_of_day[i]):
            i += 1
            continue
        e, risk, against, k = o[i + 1], a[i], 0, i + 1
        while True:
            exit_px = None
            if day_trade and last_of_day[k]:
                exit_px = c[k]
            elif k - i >= max_bars:
                exit_px = c[k]
            else:
                against = against + 1 if (m[k] - m[k - 1]) * direction < 0 else 0
                if against >= 2 and k + 1 < n:
                    exit_px = o[k + 1]
            if exit_px is not None or k + 1 >= n:
                exit_px = c[k] if exit_px is None else exit_px
                res.append(direction * (exit_px - e) / risk - COST_R)
                break
            k += 1
        i = k + 1
    return np.array(res)


def variants(sq):
    up, dn = sq.mom > 0, sq.mom < 0
    rising, falling = sq.mom > sq.mom.shift(), sq.mom < sq.mom.shift()
    stack_up = (sq.e8 > sq.e21) & (sq.e21 > sq.e34)
    stack_dn = (sq.e8 < sq.e21) & (sq.e21 < sq.e34)
    f = sq.fired & (sq.dots_before >= 5)
    return {
        "fire long (mom>0)": (sq.fired & up, 1),
        "fire short (mom<0)": (sq.fired & dn, -1),
        "fire long, >=5 dots, mom rising": (f & up & rising, 1),
        "fire short, >=5 dots, mom falling": (f & dn & falling, -1),
        "fire long + stacked EMAs": (sq.fired & up & stack_up, 1),
        "fire short + stacked EMAs": (sq.fired & dn & stack_dn, -1),
    }


def run(sym, tf, day_trade, max_bars, htf=None):
    df = load(sym, tf)
    sq = squeeze(df)
    if htf is not None:   # higher-timeframe momentum, aligned without lookahead
        hsq = squeeze(htf)
        hm = hsq.mom.shift(1).reindex(df.index, method="ffill")
    base = {d: lab_outcomes(df, sq.atr, d) for d in (1, -1)}
    rows = []
    for name, (sig, d) in variants(sq).items():
        sig = sig.fillna(False)
        if htf is not None:
            sig = sig & ((hm > 0) if d > 0 else (hm < 0))
            name += " + 60m agrees"
        o = base[d][sig].dropna()
        t = trades(df, sq, sig, d, day_trade, max_bars)
        if len(o) < 10:
            continue
        rows.append({"Sym": sym, "TF": tf, "Setup": name, "N": len(o),
                     "Hit%": f"{o.mean():.0%}", "Base%": f"{base[d].mean():.0%}",
                     "Lift": f"{(o.mean() - base[d].mean()) * 100:+.0f}pt",
                     "Trades": len(t), "Win%": f"{(t > 0).mean():.0%}",
                     "AvgR": f"{t.mean():+.2f}", "TotalR": f"{t.sum():+.1f}"})
    return rows, df.index.min(), df.index.max()


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    for tf, day_trade, max_bars in (("60m", False, 21), ("10m", True, 39)):
        rows, spans = [], set()
        for sym in ("SPY", "QQQ"):
            r, a, b = run(sym, tf, day_trade, max_bars)
            rows += r
            spans.add(f"{a:%Y-%m-%d} to {b:%Y-%m-%d}")
            if tf == "10m":
                r, *_ = run(sym, tf, day_trade, max_bars, htf=load(sym, "60m"))
                rows += r
        mode = "day trade, flat at close" if day_trade else f"swing, max {max_bars} bars"
        print(f"\n=== {tf} ({mode}) {', '.join(spans)}; lab: +{TARGET} ATR before -{STOP} ATR in {HOLD} bars")
        print(pd.DataFrame(rows).to_string(index=False))

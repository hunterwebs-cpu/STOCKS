"""The user's discretionary QQQ setup, coded:

  Long:  EMAs 8>21>34>55>89 stacked bullish AND squeeze momentum histogram
         light blue (above 0 and rising). Enter at the close of the first bar
         where both are true. Exit at the close of the first red candle
         (close < open).
  Short: mirror image: bearish stack, red histogram (below 0 and falling),
         exit at the first green candle.

Variants: require an actual squeeze fire (>=3 dots) at entry, and use Carter's
two-bar momentum-fade exit instead of the first opposite candle.

Option translation follows Carter's stated selection: ~70-delta ITM, priced
with Black-Scholes using VXN as IV (30 DTE on daily bars, 7 DTE intraday).

Run: python3 research/qqq_stack_squeeze.py
"""
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

from intraday_squeeze import load, squeeze

COST = 0.0002          # per side on the underlying
OPT_SPREAD = 0.01      # round trip, fraction of premium (ITM QQQ options)


def call_put(S, K, T, r, s, call):
    T = max(T, 1e-5)
    d1 = (np.log(S / K) + (r + s * s / 2) * T) / (s * np.sqrt(T))
    d2 = d1 - s * np.sqrt(T)
    if call:
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def strike_for_delta(S, T, r, s, call, delta=0.70):
    d1 = norm.ppf(delta) if call else -norm.ppf(delta)
    return S * np.exp(-(d1 * s * np.sqrt(T) - (r + s * s / 2) * T))


def signals(df):
    sq = squeeze(df)
    c = df.Close
    e = {n: c.ewm(span=n, adjust=False).mean() for n in (8, 21, 34, 55, 89)}
    bull = (e[8] > e[21]) & (e[21] > e[34]) & (e[34] > e[55]) & (e[55] > e[89])
    bear = (e[8] < e[21]) & (e[21] < e[34]) & (e[34] < e[55]) & (e[55] < e[89])
    rising, falling = sq.mom > sq.mom.shift(), sq.mom < sq.mom.shift()
    light_blue, red = (sq.mom > 0) & rising, (sq.mom < 0) & falling
    fire = sq.fired & (sq.dots_before >= 3)
    long_ok, short_ok = bull & light_blue, bear & red
    return sq, {
        # first bar the condition turns on
        "stack + momentum": (long_ok & ~long_ok.shift(1, fill_value=False),
                             short_ok & ~short_ok.shift(1, fill_value=False)),
        "stack + momentum + squeeze fire": (long_ok & fire, short_ok & fire),
    }


def run_trades(df, sq, entries, d, exit_rule, day_trade):
    o, c, m = df.Open.values, df.Close.values, sq.mom.values
    day = df.index.normalize()
    last = np.r_[day[1:] != day[:-1], True]
    ent = entries.fillna(False).values
    out, i, n = [], 0, len(df)
    while i < n - 1:
        if not ent[i] or (day_trade and last[i]):
            i += 1
            continue
        k, against = i + 1, 0
        while k < n - 1:
            if day_trade and last[k]:
                break
            if exit_rule == "first opposite candle":
                if (c[k] < o[k]) if d > 0 else (c[k] > o[k]):
                    break
            else:  # two bars of momentum fading
                against = against + 1 if (m[k] - m[k - 1]) * d < 0 else 0
                if against >= 2:
                    break
            k += 1
        out.append((i, k))
        i = k + 1
    return out


def option_return(df, iv, r, i, k, d, dte_days):
    S0, S1 = df.Close.iat[i], df.Close.iat[k]
    t0, t1 = df.index[i], df.index[k]
    s0 = iv.asof(t0.tz_localize(None).normalize()) if t0.tzinfo else iv.asof(t0)
    s1 = iv.asof(t1.tz_localize(None).normalize()) if t1.tzinfo else iv.asof(t1)
    rr = r.asof(t0.tz_localize(None).normalize()) if t0.tzinfo else r.asof(t0)
    T0 = dte_days / 365
    T1 = T0 - (t1 - t0).total_seconds() / (365 * 86400)
    K = strike_for_delta(S0, T0, rr, s0, d > 0)
    p0 = call_put(S0, K, T0, rr, s0, d > 0)
    p1 = call_put(S1, K, T1, rr, s1, d > 0)
    return p1 / p0 - 1 - OPT_SPREAD


def summarize(df, pairs, d, iv, r, dte):
    if not pairs:
        return None
    und = np.array([d * (df.Close.iat[k] / df.Close.iat[i] - 1) - 2 * COST for i, k in pairs])
    opt = np.array([option_return(df, iv, r, i, k, d, dte) for i, k in pairs])
    bars = np.array([k - i for i, k in pairs])
    gains, losses = opt[opt > 0], opt[opt <= 0]
    return {"N": len(pairs), "Win%": f"{(und > 0).mean():.0%}",
            "AvgUnd": f"{und.mean():+.2%}", "AvgBars": f"{bars.mean():.1f}",
            "OptAvg": f"{opt.mean():+.1%}", "OptMedian": f"{np.median(opt):+.1%}",
            "AvgWin": f"{gains.mean():+.0%}" if len(gains) else "",
            "AvgLoss": f"{losses.mean():+.0%}" if len(losses) else "",
            ">=+30%": f"{(opt >= .30).mean():.0%}", "<=-60%": f"{(opt <= -.60).mean():.0%}",
            "Worst": f"{opt.min():+.0%}"}


if __name__ == "__main__":
    vx = yf.download(["^VXN", "^IRX"], start="1999-01-01", progress=False)["Close"]
    iv, r = (vx["^VXN"] / 100).ffill(), (vx["^IRX"] / 100).ffill()
    iv.index, r.index = iv.index.tz_localize(None), r.index.tz_localize(None)
    daily = yf.download("QQQ", start="2001-02-01", auto_adjust=True, progress=False)
    daily.columns = daily.columns.get_level_values(0)
    frames = {"daily": (daily, False, 30), "60m": (load("QQQ", "60m"), False, 7),
              "10m": (load("QQQ", "10m"), True, 7)}
    rows = []
    for tf, (df, day_trade, dte) in frames.items():
        sq, sigs = signals(df)
        for name, (lsig, ssig) in sigs.items():
            for exit_rule in ("first opposite candle", "two-bar momentum fade"):
                for d, sig in ((1, lsig), (-1, ssig)):
                    s = summarize(df, run_trades(df, sq, sig, d, exit_rule, day_trade), d, iv, r, dte)
                    if s:
                        rows.append({"TF": tf, "Setup": name, "Side": "long" if d > 0 else "short",
                                     "Exit": exit_rule, **s})
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string(index=False))

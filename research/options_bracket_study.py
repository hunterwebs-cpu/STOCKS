"""Options bracket study: buy an ATM call or put, exit at +TP% or -SL% of
premium, or at a time stop. Tests whether the bracket itself has an edge and
whether simple directional signals add one.

Options are priced with Black-Scholes, using VIX (SPY) / VXN (QQQ) as the
implied vol each day, so IV expansion/crush on market moves is captured
roughly. No real chain data: no skew, no term structure, no real spreads.
Barrier checks use the underlying's daily High/Low; if both barriers could
have been hit the same day, the stop is assumed (pessimistic).

Run: python3 research/options_bracket_study.py
"""
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

START = "2005-01-01"
TP, SL = 0.30, 0.60          # +30% target, -60% stop on premium
SPREAD = 0.015               # round-trip cost as fraction of premium
DTE = 30                     # calendar days to expiry at entry
MAX_HOLD = 10                # trading days before the time stop
RISK_PER_TRADE = 0.05        # premium paid as fraction of account


def bs(S, K, T, r, sig, call):
    T = np.maximum(T, 1e-6)
    d1 = (np.log(S / K) + (r + sig**2 / 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    if call:
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def load():
    px = yf.download(["SPY", "QQQ", "^VIX", "^VXN", "^IRX"], start=START,
                     auto_adjust=False, progress=False)
    out = {}
    for t, v in (("SPY", "^VIX"), ("QQQ", "^VXN")):
        df = pd.DataFrame({k: px[k][t] for k in ("Open", "High", "Low", "Close")})
        df["iv"] = px["Close"][v] / 100
        df["r"] = px["Close"]["^IRX"] / 100
        out[t] = df.ffill().dropna()
    return out


def run_trade(df, i, call):
    """Enter at close of bar i. Returns (return on premium, exit reason, bars held)."""
    S0, K = df.Close.iat[i], round(df.Close.iat[i])
    p0 = bs(S0, K, DTE / 365, df.r.iat[i], df.iv.iat[i], call)
    tp, sl = p0 * (1 + TP), p0 * (1 - SL)
    for k in range(1, MAX_HOLD + 1):
        j = i + k
        if j >= len(df):
            return None
        T = (DTE - (df.index[j] - df.index[i]).days) / 365
        r, iv = df.r.iat[j], df.iv.iat[j]
        val = lambda S: bs(S, K, T, r, iv, call)
        o = val(df.Open.iat[j])
        hi = val(df.High.iat[j] if call else df.Low.iat[j])
        lo = val(df.Low.iat[j] if call else df.High.iat[j])
        if o <= sl:                       # gapped through the stop
            return o / p0 - 1 - SPREAD, "stop(gap)", k
        if o >= tp:                       # gapped through the target
            return o / p0 - 1 - SPREAD, "target(gap)", k
        if lo <= sl:
            return -SL - SPREAD, "stop", k
        if hi >= tp:
            return TP - SPREAD, "target", k
    return val(df.Close.iat[j]) / p0 - 1 - SPREAD, "time", MAX_HOLD


def signals(df):
    c = df.Close
    e8, e21, e34 = (c.ewm(span=n, adjust=False).mean() for n in (8, 21, 34))
    sma200 = c.rolling(200).mean()
    up = (e8 > e21) & (e21 > e34) & (c > sma200)
    dn = (e8 < e21) & (e21 < e34) & (c < sma200)
    # Pullback entry: stacked trend + close touches the 21 EMA zone
    pb_up = up & (df.Low <= e21 * 1.002) & (c > e21)
    pb_dn = dn & (df.High >= e21 * 0.998) & (c < e21)
    return {"trend-stack": (up, dn), "trend-pullback": (pb_up, pb_dn)}


def summarize(trades):
    t = pd.DataFrame(trades, columns=["ret", "why", "bars"])
    if t.empty:
        return {}
    eq = (1 + RISK_PER_TRADE * t.ret).cumprod()
    return {"Trades": len(t), "Win%": f"{(t.ret > 0).mean():.1%}",
            "AvgRet": f"{t.ret.mean():+.1%}",
            "Target%": f"{t.why.str.startswith('target').mean():.0%}",
            "Stop%": f"{t.why.str.startswith('stop').mean():.0%}",
            "GapStops": int((t.why == 'stop(gap)').sum()),
            "Time%": f"{(t.why == 'time').mean():.0%}",
            "AvgBars": f"{t.bars.mean():.1f}",
            "Acct@5%": f"{eq.iloc[-1]:.2f}x",
            "AcctMaxDD": f"{(eq / eq.cummax() - 1).min():.0%}"}


def sequential(df, long_sig, short_sig):
    trades, i = [], 200
    while i < len(df) - MAX_HOLD - 1:
        call = bool(long_sig.iat[i])
        if call or short_sig.iat[i]:
            res = run_trade(df, i, call)
            if res is None:
                break
            trades.append(res)
            i += res[2] + 1
        else:
            i += 1
    return trades


if __name__ == "__main__":
    data = load()
    rng = np.random.default_rng(7)
    rows = {}
    for t, df in data.items():
        # No-edge baseline: random direction, random days, sampled sequentially
        rand_l = pd.Series(rng.random(len(df)) < 0.5, index=df.index)
        rand_s = ~rand_l
        rows[f"{t} random coin-flip"] = summarize(sequential(df, rand_l, rand_s))
        rows[f"{t} calls only, random"] = summarize(
            sequential(df, pd.Series(True, index=df.index), pd.Series(False, index=df.index)))
        for name, (lsig, ssig) in signals(df).items():
            rows[f"{t} {name}"] = summarize(sequential(df, lsig, ssig))
    pd.set_option("display.width", 220)
    print(f"Bracket +{TP:.0%} / -{SL:.0%}, {DTE} DTE ATM, time stop {MAX_HOLD} bars, "
          f"cost {SPREAD:.1%} of premium, {START[:4]}-today\n")
    print(pd.DataFrame(rows).T.to_string())

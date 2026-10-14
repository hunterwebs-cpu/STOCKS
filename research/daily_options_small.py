"""Daily-chart swing version of the user's setup, traded with options on
affordable, liquid names (small-account universe).

Setup: EMAs 8/21/34/55/89 stacked + squeeze momentum light blue (red for
puts), first bar it turns on; optional: only on a squeeze fire. Exit: first
opposite candle, or Carter's two-bar momentum fade. Option: ~0.70 delta, 30
DTE (Carter's selection), priced with Black-Scholes using 20-day realized
vol x 1.15 as an IV proxy (no historical chains). Round-trip spread cost 5%
of premium.

Run: python3 research/daily_options_small.py
"""
import numpy as np
import pandas as pd
import yfinance as yf

from qqq_stack_squeeze import call_put, run_trades, signals, strike_for_delta

SYMS = ["SOFI", "F", "AAL", "SNAP", "RIVN", "NIO", "T", "PFE", "GRAB"]
SPREAD, DTE, RATE = 0.05, 30, 0.04


def option_ret(df, iv, i, k, d):
    S0, S1 = df.Close.iat[i], df.Close.iat[k]
    T0 = DTE / 365
    T1 = T0 - (df.index[k] - df.index[i]).days / 365
    K = strike_for_delta(S0, T0, RATE, iv.iat[i], d > 0)
    p0 = call_put(S0, K, T0, RATE, iv.iat[i], d > 0)
    p1 = call_put(S1, K, T1, RATE, iv.iat[k], d > 0)
    return p1 / p0 - 1 - SPREAD, p0 * 100


rows = []
for sym in SYMS:
    df = yf.download(sym, start="2015-01-01", auto_adjust=True, progress=False)
    df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    iv = (np.log(df.Close).diff().rolling(20).std() * np.sqrt(252) * 1.15).bfill()
    sq, sigs = signals(df)
    for name, (lsig, ssig) in sigs.items():
        for exit_rule in ("first opposite candle", "two-bar momentum fade"):
            for d, sig in ((1, lsig), (-1, ssig)):
                pairs = run_trades(df, sq, sig, d, exit_rule, False)
                if len(pairs) < 10:
                    continue
                r = [option_ret(df, iv, i, k, d) for i, k in pairs]
                ret = np.array([x[0] for x in r])
                cost = np.mean([x[1] for x in r])
                half = len(ret) // 2
                rows.append({"sym": sym, "setup": name.replace("stack + momentum", "stack+mom"),
                             "side": "call" if d > 0 else "put", "exit": exit_rule.split()[0],
                             "N": len(ret), "win%": round((ret > 0).mean() * 100),
                             "avg%": round(ret.mean() * 100, 1), "median%": round(np.median(ret) * 100, 1),
                             "PF": round(ret[ret > 0].sum() / max(-ret[ret < 0].sum(), 1e-9), 2),
                             "avg% 1st/2nd half": f"{ret[:half].mean()*100:+.0f} / {ret[half:].mean()*100:+.0f}",
                             "avg_cost$": round(cost), "hold_days": round(np.mean([k - i for i, k in pairs]), 1)})

t = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print("All variants with >=10 trades, sorted by avg option return:")
print(t.sort_values("avg%", ascending=False).to_string(index=False))
robust = t[(t.N >= 30) & (t["avg%"] > 0) & (t.PF > 1.2)]
robust = robust[robust["avg% 1st/2nd half"].apply(lambda s: all(float(x) > 0 for x in s.split(" / ")))]
print("\nPositive in BOTH halves, N>=30, PF>1.2:")
print(robust.to_string(index=False) if len(robust) else "none")

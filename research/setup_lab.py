"""Setup lab: measure whether a setup is genuinely high-probability.

For every occurrence of a setup, check what the underlying did next: did it
reach +TARGET ATR in the trade's direction before -STOP ATR against it,
within HOLD bars? Compare that hit rate with the base rate for the same
direction on every bar. Only the gap (lift) is edge; the raw hit rate is
mostly set by where the target and stop sit.

TARGET=1 ATR / STOP=2 ATR over 5 days is a rough underlying-equivalent of the
+30% / -60% bracket on a 30-DTE ATM SPY option. Same-bar ambiguity counts as
a loss.

Run: python3 research/setup_lab.py
"""
import numpy as np
import pandas as pd
import yfinance as yf

START = "2000-01-01"
TARGET, STOP, HOLD = 1.0, 2.0, 5
MIN_N = 30


def load(tickers):
    d = yf.download(tickers, start=START, auto_adjust=True, progress=False)
    return {t: d.xs(t, axis=1, level=1).dropna() for t in tickers}


def indicators(df):
    c, h, l = df.Close, df.High, df.Low
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    x = pd.DataFrame(index=df.index)
    x["atr"] = tr.rolling(14).mean()
    for n in (8, 21, 34):
        x[f"e{n}"] = c.ewm(span=n, adjust=False).mean()
    x["sma200"] = c.rolling(200).mean()
    # TTM squeeze (BB 20/2 inside KC 20/1.5)
    sma, sd, atr20 = c.rolling(20).mean(), c.rolling(20).std(ddof=0), tr.rolling(20).mean()
    x["sq_on"] = (2 * sd) < (1.5 * atr20)
    mid = ((h.rolling(20).max() + l.rolling(20).min()) / 2 + sma) / 2
    x["mom"] = (c - mid).rolling(5).mean()
    # RSI(2)
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=.5).mean(), (-d.clip(upper=0)).ewm(alpha=.5).mean()
    x["rsi2"] = 100 - 100 / (1 + up / dn)
    return x


def setups(df, x):
    c = df.Close
    stacked_up = (x.e8 > x.e21) & (x.e21 > x.e34)
    stacked_dn = (x.e8 < x.e21) & (x.e21 < x.e34)
    fired = x.sq_on.shift(1, fill_value=False) & ~x.sq_on
    down3 = (c < c.shift()) & (c.shift() < c.shift(2)) & (c.shift(2) < c.shift(3))
    up3 = (c > c.shift()) & (c.shift() > c.shift(2)) & (c.shift(2) > c.shift(3))
    return {
        # name: (signal series, direction +1 long / -1 short)
        "squeeze fire, mom up": (fired & (x.mom > 0), 1),
        "squeeze fire, mom down": (fired & (x.mom < 0), -1),
        "squeeze fire up + stacked EMAs": (fired & (x.mom > 0) & stacked_up, 1),
        "21 EMA pullback, stacked up": (stacked_up & (df.Low <= x.e21) & (c > x.e21), 1),
        "21 EMA rally, stacked down": (stacked_dn & (df.High >= x.e21) & (c < x.e21), -1),
        "RSI2<10 above 200SMA": ((x.rsi2 < 10) & (c > x.sma200), 1),
        "RSI2>90 below 200SMA": ((x.rsi2 > 90) & (c < x.sma200), -1),
        "3 down days above 200SMA": (down3 & (c > x.sma200), 1),
        "3 up days below 200SMA": (up3 & (c < x.sma200), -1),
    }


def outcomes(df, atr, direction):
    """For each bar: 1 if target hit before stop within HOLD bars, else 0."""
    c, h, l = df.Close.values, df.High.values, df.Low.values
    a = atr.values
    n = len(df)
    res = np.full(n, np.nan)
    for i in range(n - HOLD):
        if np.isnan(a[i]):
            continue
        tgt = c[i] + direction * TARGET * a[i]
        stp = c[i] - direction * STOP * a[i]
        hit = 0
        for j in range(i + 1, i + HOLD + 1):
            fav = h[j] >= tgt if direction > 0 else l[j] <= tgt
            adv = l[j] <= stp if direction > 0 else h[j] >= stp
            if adv:
                break
            if fav:
                hit = 1
                break
        res[i] = hit
    return pd.Series(res, index=df.index)


def gap_fill_table(df):
    """Day-trade setup from Mastering the Trade: does an opening gap fill
    (trade back to prior close) the same session? Daily bars suffice."""
    pc = df.Close.shift()
    gap = (df.Open / pc - 1) * 100
    filled = np.where(gap < 0, df.High >= pc, df.Low <= pc)
    t = pd.DataFrame({"gap": gap, "filled": filled}).dropna()
    bins = [-99, -1, -0.5, -0.25, -0.1, 0.1, 0.25, 0.5, 1, 99]
    t["bucket"] = pd.cut(t.gap, bins)
    g = t[t.gap.abs() >= 0.1].groupby("bucket", observed=True).filled.agg(["count", "mean"])
    g["mean"] = (g["mean"] * 100).round(1).astype(str) + "%"
    return g.rename(columns={"count": "N", "mean": "Fill same day"})


def walk_halves(sig, out):
    """Hit rate in first vs second half of the sample — a crude stability check."""
    s = out[sig.fillna(False).astype(bool)].dropna()
    mid = len(out) // 2
    cut = out.index[mid]
    a, b = s[s.index < cut], s[s.index >= cut]
    return a.mean() if len(a) else np.nan, b.mean() if len(b) else np.nan


if __name__ == "__main__":
    data = load(["SPY", "QQQ"])
    rows = []
    for t, df in data.items():
        x = indicators(df)
        base = {d: outcomes(df, x.atr, d) for d in (1, -1)}
        for name, (sig, d) in setups(df, x).items():
            o = base[d][sig.fillna(False).astype(bool)].dropna()
            if len(o) < MIN_N:
                continue
            b = base[d].dropna().mean()
            h1, h2 = walk_halves(sig, base[d])
            rows.append({"Ticker": t, "Setup": name, "N": len(o),
                         "Hit%": f"{o.mean():.1%}", "Base%": f"{b:.1%}",
                         "Lift": f"{(o.mean() - b) * 100:+.1f}pt",
                         "1st half": f"{h1:.0%}", "2nd half": f"{h2:.0%}"})
    pd.set_option("display.width", 220)
    print(f"Target +{TARGET} ATR before -{STOP} ATR within {HOLD} bars, {START[:4]}-today\n")
    print(pd.DataFrame(rows).to_string(index=False))
    for t, df in data.items():
        print(f"\n{t} opening gap fills (same session):")
        print(gap_fill_table(df).to_string())

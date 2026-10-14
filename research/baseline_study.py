"""Baseline study: what do SPY/QQQ, a mechanical TTM Squeeze swing system,
and simple leverage actually return? Used to sanity-check a 30%/yr target.

Run: python3 research/baseline_study.py  (needs yfinance, pandas, numpy)
"""
import numpy as np
import pandas as pd
import yfinance as yf

START = "2000-01-01"
COST_BPS = 2.0  # per side, commission + slippage, applied on each entry/exit


def load(tickers):
    d = yf.download(tickers, start=START, auto_adjust=True, progress=False)
    return {t: d.xs(t, axis=1, level=1).dropna() for t in tickers}


def stats(equity: pd.Series, trades=None):
    r = equity.pct_change().dropna()
    yrs = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / yrs) - 1
    dd = (equity / equity.cummax() - 1).min()
    sharpe = r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan
    yearly = equity.resample("YE").last().pct_change().dropna()
    out = {"CAGR": cagr, "MaxDD": dd, "Sharpe": sharpe,
           "Yrs>=30%": f"{(yearly >= .30).sum()}/{len(yearly)}",
           "WorstYr": yearly.min()}
    if trades is not None and len(trades):
        t = np.array(trades)
        out.update({"Trades": len(t), "Win%": (t > 0).mean(),
                    "AvgTrade": t.mean()})
    return out


def ttm_squeeze(df, n=20, bb_k=2.0, kc_k=1.5):
    c, h, l = df.Close, df.High, df.Low
    sma = c.rolling(n).mean()
    sd = c.rolling(n).std(ddof=0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    sq_on = (sma - bb_k * sd > sma - kc_k * atr) & (sma + bb_k * sd < sma + kc_k * atr)
    mid = ((h.rolling(n).max() + l.rolling(n).min()) / 2 + sma) / 2
    x = np.arange(n)

    def linreg_end(y):  # value of least-squares line at the last bar
        b, a = np.polyfit(x, y, 1)
        return a + b * (n - 1)

    mom = (c - mid).rolling(n).apply(linreg_end, raw=True)
    fired = sq_on.shift(1, fill_value=False) & ~sq_on
    return mom, fired


def backtest_squeeze(df, allow_short=False):
    """Signal on close, fill next open. Exit after 2 consecutive bars of
    momentum moving against the position (Carter's 'two bars' rule)."""
    mom, fired = ttm_squeeze(df)
    o, c = df.Open.values, df.Close.values
    m = mom.values
    f = fired.values
    eq = np.ones(len(df))
    pos, entry, trades, against = 0, 0.0, [], 0
    cash = 1.0
    for i in range(1, len(df) - 1):
        # mark to market
        if pos:
            eq[i] = cash * (1 + pos * (c[i] / entry - 1))
        else:
            eq[i] = cash
        if np.isnan(m[i]) or np.isnan(m[i - 1]):
            continue
        if pos:
            against = against + 1 if (m[i] - m[i - 1]) * pos < 0 else 0
            if against >= 2:
                ret = pos * (o[i + 1] / entry - 1) - 2 * COST_BPS / 1e4
                cash *= 1 + ret
                trades.append(ret)
                pos, against = 0, 0
        elif f[i]:
            if m[i] > 0 and m[i] > m[i - 1]:
                pos = 1
            elif allow_short and m[i] < 0 and m[i] < m[i - 1]:
                pos = -1
            if pos:
                entry, against = o[i + 1], 0
    eq[-1] = eq[-2]
    return pd.Series(eq, index=df.index), trades


def leveraged(df, lev, rate):
    r = df.Close.pct_change().fillna(0)
    daily_fin = (lev - 1) * rate.reindex(df.index).ffill().fillna(0) / 252
    return (1 + lev * r - daily_fin).cumprod()


def fmt(d):
    return {k: (f"{v:.1%}" if isinstance(v, float) and k not in ("Sharpe",)
                else f"{v:.2f}" if k == "Sharpe" else v) for k, v in d.items()}


if __name__ == "__main__":
    etfs = ["SPY", "QQQ"]
    # Survivorship-biased on purpose: today's mega-cap options names.
    stocks = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD"]
    data = load(etfs + stocks)
    irx = yf.download("^IRX", start=START, progress=False, auto_adjust=True)["Close"].squeeze() / 100

    rows = {}
    for t in etfs:
        bh = data[t].Close / data[t].Close.iloc[0]
        rows[f"{t} buy&hold"] = stats(bh)
        eq, tr = backtest_squeeze(data[t])
        rows[f"{t} squeeze long"] = stats(eq, tr)
        eq, tr = backtest_squeeze(data[t], allow_short=True)
        rows[f"{t} squeeze L/S"] = stats(eq, tr)
    for lev in (1.5, 2, 3):
        rows[f"SPY {lev}x daily lev"] = stats(leveraged(data["SPY"], lev, irx))
        rows[f"QQQ {lev}x daily lev"] = stats(leveraged(data["QQQ"], lev, irx))

    # Squeeze on mega-caps, equal-weight average of per-stock trade results
    all_tr = []
    for t in stocks:
        _, tr = backtest_squeeze(data[t])
        all_tr += tr
    t = np.array(all_tr)
    mega = {"Trades": len(t), "Win%": f"{(t > 0).mean():.1%}",
            "AvgTrade": f"{t.mean():.2%}", "MedianTrade": f"{np.median(t):.2%}"}

    pd.set_option("display.width", 200)
    table = pd.DataFrame({k: fmt(v) for k, v in rows.items()}).T.fillna("")
    print(table.to_string())
    print("\nSqueeze long on 8 mega-caps (SURVIVORSHIP-BIASED):", mega)

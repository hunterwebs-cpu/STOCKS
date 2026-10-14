"""0DTE SPY/QQQ option tests on 5-min bars (Yahoo: last ~60 days only).

A) "One strike" scalp (user's method): buy a 0DTE option 2 strikes OTM,
   sell when the underlying moves $1 (one strike) in your favor. Stop when it
   moves $1 against, or after 60 minutes / at 15:55. Windows: before lunch
   (09:45-11:30) and 15:00-15:30.
B) Power hour (buddy's method): buy at 15:00 / 15:15 / 15:30, sell at the
   15:55 bar close. ATM, 1 OTM and 2 OTM strikes.

Direction choices: calls only, puts only, the user's setup (10-min EMA stack
+ squeeze momentum, using the last completed 10-min bar), and trend (price
vs. the day's VWAP).

Pricing: Black-Scholes with time to the 16:00 close. IV = prior day's
VIX1D close (SPY) or VIX1D x VXN/VIX (QQQ). It's a model, not real
fills; 0DTE IV in the last hour behaves differently. Costs: $0.02/share
round-trip spread + $0.10/contract fees.

Run: python3 research/zero_dte_study.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from trader.indicators import setup_frame  # noqa: E402

NY = "America/New_York"
SPREAD, FEES = 0.02, 0.10
# IV multipliers (market IV / model IV) by (symbol, is_call, strikes OTM),
# fitted to real next-day SPY/QQQ quotes on 2026-10-14 by calibrate().
# Captures put skew and QQQ's richer pricing; assumes the shape is stable.
IV_MULT = {}
MIN_YEAR = 365 * 24 * 60


def bs(S, K, minutes, sig, call, r=0.04):
    T = max(minutes, 0.5) / MIN_YEAR
    d1 = (np.log(S / K) + (r + sig * sig / 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    if call:
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def mins_to_close(ts):
    return (ts.normalize() + pd.Timedelta(hours=16) - ts).total_seconds() / 60


DATA = Path(__file__).resolve().parent.parent / "data"


def _bars(sym, px):
    f = DATA / f"{sym}_5m.csv"
    if f.exists():
        df = pd.read_csv(f)
        df.index = pd.to_datetime(df.pop("Datetime"), utc=True).tz_convert(NY)
        return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    df = pd.DataFrame({k: px[k][sym] for k in ("Open", "High", "Low", "Close", "Volume")}).dropna()
    df.index = df.index.tz_convert(NY)
    return df


def load():
    use_csv = all((DATA / f"{s}_5m.csv").exists() for s in ("SPY", "QQQ"))
    px = None if use_csv else yf.download(["SPY", "QQQ"], period="60d", interval="5m", progress=False)
    vol = yf.download(["^VIX1D", "^VIX", "^VXN"], start="2023-04-01", progress=False)["Close"].ffill()
    vol.index = vol.index.tz_localize(None)
    iv = {"SPY": vol["^VIX1D"] / 100, "QQQ": vol["^VIX1D"] * vol["^VXN"] / vol["^VIX"] / 100}
    out = {}
    for s in ("SPY", "QQQ"):
        df = _bars(s, px).between_time("09:30", "15:55")
        # prior day's vol index close = today's IV
        prior = iv[s].shift(1)          # prior day's close is today's IV
        days = pd.DatetimeIndex(df.index.tz_localize(None).normalize())
        u = days.unique()
        per_day = prior.reindex(prior.index.union(u)).ffill().reindex(u)
        df["iv"] = per_day.reindex(days).values
        # VWAP
        tp = (df.High + df.Low + df.Close) / 3
        g = df.index.date
        df["vwap"] = (tp * df.Volume).groupby(g).cumsum() / df.Volume.groupby(g).cumsum()
        # user's setup on 10-min bars, known at each 5-min close
        b10 = df.resample("10min", origin="start_day", offset="30min").agg(
            {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        st = setup_frame(b10)
        st.index = st.index + pd.Timedelta(minutes=10)     # known at bar end
        bull = (st.bull & st.light_blue).astype(float).reindex(st.index.union(df.index + pd.Timedelta(minutes=5))).ffill()
        bear = (st.bear & st.red).astype(float).reindex(bull.index).ffill()
        df["setup_bull"] = bull.reindex(df.index + pd.Timedelta(minutes=5)).values == 1
        df["setup_bear"] = bear.reindex(df.index + pd.Timedelta(minutes=5)).values == 1
        out[s] = df.dropna(subset=["iv"])
    return out


def direction(row, how):
    if how == "calls":
        return 1
    if how == "puts":
        return -1
    if how == "setup":
        return 1 if row.setup_bull else (-1 if row.setup_bear else 0)
    if how == "trend (VWAP)":
        return 1 if row.Close > row.vwap else -1
    raise ValueError(how)


def calibrate():
    """Fit IV multipliers so the model matches today's next-day quotes."""
    from scipy.optimize import brentq
    vol = yf.download(["^VIX1D", "^VIX", "^VXN"], period="5d", progress=False)["Close"].ffill().iloc[-1]
    for s in ("SPY", "QQQ"):
        tk = yf.Ticker(s)
        S = tk.history(period="1d").Close.iloc[-1]
        ch = tk.option_chain(tk.options[1])
        iv = vol["^VIX1D"] / 100 * (1 if s == "SPY" else vol["^VXN"] / vol["^VIX"])
        for call, df in ((True, ch.calls), (False, ch.puts)):
            for otm in (0, 1, 2):
                K = (np.floor(S) + otm) if call else (np.ceil(S) - otm)
                r = df[df.strike == K].iloc[0]
                mid = (r.bid + r.ask) / 2
                m = brentq(lambda k: bs(S, K, 24 * 60, iv * k, call) - mid, 0.1, 10)
                IV_MULT[(s, call, otm)] = round(m, 3)
    return IV_MULT


def entry_price(row, t, d, otm, sym=None):
    S = row.Close
    K = (np.floor(S) + otm) if d > 0 else (np.ceil(S) - otm)
    if otm == 0:
        K = round(S)
    iv = row.iv * IV_MULT.get((sym, d > 0, otm), 1.0)
    p = bs(S, K, mins_to_close(t + pd.Timedelta(minutes=5)), iv, d > 0)
    return K, p, iv


def one_strike(df, times, how, otm=2, move=1.0, stop_move=1.0, max_hold=60, sym=None,
               max_per_day=None, quit_on_win=False):
    """max_per_day / quit_on_win implement "hit and quit": stop for the day
    after the first winner, and/or after N attempts."""
    trades = []
    for day, g in df.groupby(df.index.date):
        busy_until, n_today, won = None, 0, False
        for t, row in g.iterrows():
            if (quit_on_win and won) or (max_per_day and n_today >= max_per_day):
                break
            if t.strftime("%H:%M") not in times or (busy_until is not None and t <= busy_until):
                continue
            d = direction(row, how)
            if d == 0:
                continue
            K, p0, _ = entry_price(row, t, d, otm, sym)
            mult = IV_MULT.get((sym, d > 0, otm), 1.0)
            S0 = row.Close
            tgt, stp = S0 + d * move, S0 - d * stop_move
            later = g[g.index > t]
            exit_val, why, t_out = None, None, None
            for t2, r2 in later.iterrows():
                m = mins_to_close(t2 + pd.Timedelta(minutes=5))
                adverse = (r2.Low <= stp) if d > 0 else (r2.High >= stp)
                fav = (r2.High >= tgt) if d > 0 else (r2.Low <= tgt)
                if adverse:
                    exit_val, why = bs(stp, K, m, r2.iv * mult, d > 0), "stop"
                elif fav:
                    exit_val, why = bs(tgt, K, m, r2.iv * mult, d > 0), "target"
                elif (t2 - t).total_seconds() / 60 >= max_hold or t2.strftime("%H:%M") >= "15:55":
                    exit_val, why = bs(r2.Close, K, m, r2.iv * mult, d > 0), "time"
                if why:
                    t_out = t2
                    break
            if why is None:
                continue
            pnl = (exit_val - p0 - SPREAD) * 100 - FEES
            trades.append({"day": day, "t": t, "side": d, "cost": (p0 + SPREAD / 2) * 100,
                           "pnl": pnl, "ret": pnl / ((p0 + SPREAD / 2) * 100), "why": why})
            busy_until, n_today, won = t_out, n_today + 1, pnl > 0
    return pd.DataFrame(trades)


def power_hour(df, entry, how, otm, sym=None):
    trades = []
    for day, g in df.groupby(df.index.date):
        if entry not in g.index.strftime("%H:%M") or "15:55" not in g.index.strftime("%H:%M"):
            continue
        row = g[g.index.strftime("%H:%M") == entry].iloc[0]
        t = g.index[g.index.strftime("%H:%M") == entry][0]
        d = direction(row, how)
        if d == 0:
            continue
        K, p0, iv = entry_price(row, t, d, otm, sym)
        last = g[g.index.strftime("%H:%M") == "15:55"].iloc[0]
        p1 = max(0.0, (last.Close - K) if d > 0 else (K - last.Close))   # ~expiry value
        p1 = max(p1, bs(last.Close, K, 5, iv, d > 0))
        pnl = (p1 - p0 - SPREAD) * 100 - FEES
        trades.append({"day": day, "t": t, "side": d, "cost": (p0 + SPREAD / 2) * 100,
                       "pnl": pnl, "ret": pnl / ((p0 + SPREAD / 2) * 100), "why": "close"})
    return pd.DataFrame(trades)


def summarize(t, **labels):
    if t.empty:
        return None
    return {**labels, "N": len(t), "win%": round((t.pnl > 0).mean() * 100),
            "avg_cost$": round(t.cost.mean()), "avg_ret%": round(t.ret.mean() * 100, 1),
            "median_ret%": round(t.ret.median() * 100, 1), "total$_1_contract": round(t.pnl.sum()),
            "target%": round((t.why == "target").mean() * 100) if "why" in t else None}


def account_sim(t, start=500.0, frac=0.20):
    """Spend up to `frac` of equity per day on premium (whole contracts)."""
    eq, path = start, []
    for day, g in t.groupby("day"):
        budget = frac * eq
        for _, r in g.iterrows():
            n = int(budget // r.cost)
            if n < 1:
                continue
            eq += n * r.pnl
            budget -= n * r.cost
        path.append(eq)
        if eq <= 0:
            break
    p = pd.Series(path)
    return eq, (p / p.cummax() - 1).min() if len(p) else 0


if __name__ == "__main__":
    data = load()
    print("IV multipliers (market / model):", calibrate())
    pd.set_option("display.width", 250)
    morning = [f"{h:02d}:{m:02d}" for h in (9, 10, 11) for m in range(0, 60, 15)
               if "09:45" <= f"{h:02d}:{m:02d}" <= "11:30"]
    afternoon = ["15:00", "15:15", "15:30"]
    hows = ["calls", "puts", "setup", "trend (VWAP)"]

    rows, keep = [], {}
    for s, df in data.items():
        for wname, times in (("before lunch", morning), ("3:00-3:30pm", afternoon)):
            for how in hows:
                t = one_strike(df, set(times), how, sym=s)
                r = summarize(t, sym=s, test="one-strike, 2 OTM", window=wname, direction=how)
                if r:
                    rows.append(r)
                    keep[(s, "A", wname, how)] = t
    print(f"A) One-strike scalp, {data['SPY'].index[0]:%Y-%m-%d} to {data['SPY'].index[-1]:%Y-%m-%d}")
    print(pd.DataFrame(rows).to_string(index=False))

    rows = []
    for s, df in data.items():
        for entry in afternoon:
            for otm in (0, 1, 2):
                for how in hows:
                    t = power_hour(df, entry, how, otm, sym=s)
                    r = summarize(t, sym=s, test=f"power hour, {('ATM' if otm == 0 else f'{otm} OTM')}",
                                  entry=entry, direction=how)
                    if r:
                        r.pop("target%")
                        rows.append(r)
                        keep[(s, "B", entry, otm, how)] = t
    print("\nB) Power hour: buy at entry, sell 15:55")
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n$500 account, spending up to 20% of equity per day on premium:")
    for key in [("QQQ", "A", "before lunch", "setup"), ("QQQ", "A", "3:00-3:30pm", "setup"),
                ("SPY", "A", "before lunch", "setup"), ("QQQ", "B", "15:00", 2, "trend (VWAP)"),
                ("QQQ", "B", "15:30", 2, "trend (VWAP)"), ("SPY", "B", "15:00", 2, "trend (VWAP)")]:
        if key in keep:
            eq, dd = account_sim(keep[key])
            print(f"  {key}: $500 -> ${eq:,.0f}  (max drawdown {dd:.0%})")

"""Daily swing setups from Mastering the Trade, traded with ~30-DTE options on
cheap (< $30 at the time), liquid names, scanned every day.

Universe: ~60 liquid optionable names, daily data 2015+ (yfinance). A name is
eligible on a day only if its *actual* price then was < MAX_PRICE and its
20-day average dollar volume > MIN_DVOL. Survivorship bias: the list is
today's survivors; cheap names that went bankrupt or delisted are missing,
which flatters results.

Setups (see SETUPS): squeeze fire with stacked EMAs; squeeze scale-in on
pullback to the 8/21 EMA; HOLP/LOHP reversal; and the user's stack +
momentum entry for comparison.

Exits:
  carter: Carter's daily options plan on the underlying: stop 2xATR(21);
          time stop 3 days if not profitable; 1/3 off at the prior 20-day
          extreme (stop to 1 ATR), 1/3 at +2 ATR (stop to entry), trail the
          last 1/3 with the 3-day low/high. Max 15 days.
  bracket: option +30% target / -50% stop, max 10 days ("hit and quit").

Options: Black-Scholes, IV = 20-day realized vol x1.15 (calls) / x1.30
(puts; skew guess). No historical chains, so every result here is modeled.
Round-trip spread SPREAD of premium (cheap names are wide).

Run: python3 research/mtt_swing.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

DATA = Path("/tmp/claude-0/-home-user-STOCKS/eefa142c-ebfb-56eb-8ce6-0f2f11b18965/scratchpad/daily")
MAX_PRICE, MIN_DVOL = 30.0, 50e6
DTE, RATE = 30, 0.04
SPREAD = 0.08
IV_MULT = {True: 1.15, False: 1.30}


# ---------- pricing ----------
def bs(S, K, T, sig, call):
    T = max(T, 1e-4)
    d1 = (np.log(S / K) + (RATE + sig * sig / 2) * T) / (sig * np.sqrt(T))
    d2 = d1 - sig * np.sqrt(T)
    if call:
        return S * norm.cdf(d1) - K * np.exp(-RATE * T) * norm.cdf(d2)
    return K * np.exp(-RATE * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def strike(S, sig, call, delta):
    if delta == "ATM":
        return S
    T = DTE / 365
    d1 = norm.ppf(delta) if call else -norm.ppf(delta)
    return S * np.exp(-(d1 * sig * np.sqrt(T) - (RATE + sig * sig / 2) * T))


# ---------- data + indicators ----------
def load(sym):
    df = pd.read_csv(DATA / f"{sym}.csv", index_col=0, parse_dates=True)
    df = df[["Open", "High", "Low", "Close", "Volume", "Stock Splits"]].dropna(subset=["Close"])
    # yfinance prices are split-adjusted; rebuild the price actually seen then
    factor = pd.Series(1.0, index=df.index)
    for when, ratio in df["Stock Splits"][df["Stock Splits"] > 0].items():
        factor[df.index < when] *= ratio
    df["raw_close"] = df.Close * factor
    c, h, l = df.Close, df.High, df.Low
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr21"] = tr.rolling(21).mean()
    df["dvol"] = (df.raw_close * df.Volume / factor).rolling(20).mean()  # shares were unadjusted too
    df["rv"] = np.log(c).diff().rolling(20).std() * np.sqrt(252)
    for n in (8, 21, 34, 55, 89):
        df[f"e{n}"] = c.ewm(span=n, adjust=False).mean()
    sma, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    df["sq_on"] = (2 * sd) < (1.5 * tr.rolling(20).mean())
    df["dots"] = df.sq_on.groupby((~df.sq_on).cumsum()).cumsum()
    delta = c - ((h.rolling(20).max() + l.rolling(20).min()) / 2 + sma) / 2
    x = np.arange(20)
    w = 1 / 20 + (x - x.mean()) * (19 - x.mean()) / ((x - x.mean()) ** 2).sum()
    mom = np.full(len(df), np.nan)
    if len(df) >= 20:
        mom[19:] = np.convolve(delta.to_numpy(), w[::-1], mode="valid")
    df["mom"] = mom
    df["near_high"] = c >= 0.9 * h.rolling(252, min_periods=120).max()
    df["near_low"] = c <= 1.1 * l.rolling(252, min_periods=120).min()
    df["hi20_prev"] = h.rolling(20).max().shift(1)
    df["lo20_prev"] = l.rolling(20).min().shift(1)
    return df.dropna(subset=["atr21", "rv", "mom", "dvol"])


def holp_lohp(df, n=20):
    """HOLP (Mastering the Trade ch. 17, via secondary sources): the bar with
    the lowest low of the last n bars; buy on a CLOSE above that bar's high.
    LOHP mirrors it for shorts. Stop at the extreme bar, then a 2-bar trailing
    stop from day 3, no target (exit kind "holp")."""
    h, l, c = df.High.values, df.Low.values, df.Close.values
    lowest = df.Low.rolling(n).min().values
    highest = df.High.rolling(n).max().values
    buy, sell = np.zeros(len(df), bool), np.zeros(len(df), bool)
    for i in range(n, len(df)):
        for j in range(max(n, i - 5), i):
            if l[j] == lowest[j] and c[i] > h[j] and c[i - 1] <= h[j]:
                buy[i] = True
            if h[j] == highest[j] and c[i] < l[j] and c[i - 1] >= l[j]:
                sell[i] = True
    return pd.Series(buy, df.index), pd.Series(sell, df.index)


def setups(df):
    c = df.Close
    bull = (df.e8 > df.e21) & (df.e21 > df.e34)
    bear = (df.e8 < df.e21) & (df.e21 < df.e34)
    bull5 = bull & (df.e34 > df.e55) & (df.e55 > df.e89)
    bear5 = bear & (df.e34 < df.e55) & (df.e55 < df.e89)
    rising = df.mom > df.mom.shift()
    fired = df.sq_on.shift(1, fill_value=False) & ~df.sq_on & (df.dots.shift(1) >= 3)
    pull_up = bull & df.sq_on & (df.dots >= 5) & (df.Low <= df.e8) & (c > df.e21)
    pull_dn = bear & df.sq_on & (df.dots >= 5) & (df.High >= df.e8) & (c < df.e21)
    lb, ls = (bull5 & (df.mom > 0) & rising), (bear5 & (df.mom < 0) & ~rising)
    hb, hs = holp_lohp(df)
    up_trend, dn_trend = df.e21 > df.e55, df.e21 < df.e55
    hi_ok, lo_ok = df.near_high & (c > df.e34), df.near_low & (c < df.e34)   # Carter: near 52-wk high, above 34 MA
    return {
        "squeeze fire + stacked EMAs": (fired & (df.mom > 0) & bull & (c > df.e21), fired & (df.mom < 0) & bear & (c < df.e21)),
        "Carter plan: squeeze fire near 52-wk high": (fired & (df.mom > 0) & bull & hi_ok, fired & (df.mom < 0) & bear & lo_ok),
        "squeeze scale-in (8 EMA pullback)": (pull_up, pull_dn),
        "Carter plan: scale-in near 52-wk high": (pull_up & hi_ok, pull_dn & lo_ok),
        "HOLP / LOHP (with trend)": (hb & up_trend, hs & dn_trend),
        "user: stack + momentum (first bar)": (lb & ~lb.shift(1, fill_value=False), ls & ~ls.shift(1, fill_value=False)),
    }


# ---------- trade simulation (per signal, 1 contract) ----------
def simulate(df, i, d, exit_kind, delta):
    call = d > 0
    S0, sig = df.Close.iat[i], df.rv.iat[i] * IV_MULT[call]
    K = strike(S0, sig, call, delta)
    p0 = bs(S0, K, DTE / 365, sig, call)
    atr = df.atr21.iat[i]
    entry = S0
    stop = S0 - d * 2 * atr
    t1 = df.hi20_prev.iat[i] if call else df.lo20_prev.iat[i]
    if (t1 - S0) * d < 0.5 * atr:
        t1 = S0 + d * atr
    t2 = S0 + d * 2 * atr
    remaining, realized = 1.0, 0.0
    max_days = 15 if exit_kind in ("carter", "holp") else 10
    if exit_kind == "holp":
        n = 20
        win = df.iloc[max(0, i - n + 1):i + 1]
        stop = win.Low.min() if call else win.High.max()

    def opt(S, k, iv):
        return bs(S, K, (DTE - (df.index[k] - df.index[i]).days) / 365, iv, call)

    for k in range(i + 1, min(i + max_days + 1, len(df))):
        o, hi, lo, c = df.Open.iat[k], df.High.iat[k], df.Low.iat[k], df.Close.iat[k]
        iv = df.rv.iat[k] * IV_MULT[call]
        fav, adv = (hi, lo) if call else (lo, hi)
        if exit_kind == "holp":
            if (adv - stop) * d <= 0:
                px = o if (o - stop) * d <= 0 else stop
                return opt(px, k, iv) / p0 - 1 - SPREAD, k - i
            if k - i >= 2:   # from the 3rd bar: trail at the low/high of the bar two back
                trail = df.Low.iat[k - 1] if call else df.High.iat[k - 1]
                stop = max(stop, trail) if call else min(stop, trail)
            continue
        if exit_kind == "bracket":
            v_adv, v_fav = opt(adv, k, iv), opt(fav, k, iv)
            if v_adv <= p0 * 0.5:
                return min(opt(o, k, iv), p0 * 0.5) / p0 - 1 - SPREAD, k - i
            if v_fav >= p0 * 1.3:
                return max(opt(o, k, iv), p0 * 1.3) / p0 - 1 - SPREAD, k - i
            continue
        # carter plan on the underlying
        if (adv - stop) * d <= 0:
            px = o if (o - stop) * d <= 0 else stop
            return realized + remaining * (opt(px, k, iv) / p0 - 1) - SPREAD, k - i
        if remaining > 0.67 and (fav - t1) * d >= 0:
            realized += (1 / 3) * (opt(t1, k, iv) / p0 - 1)
            remaining -= 1 / 3
            stop = S0 - d * atr
        if 0.34 < remaining <= 0.67 and (fav - t2) * d >= 0:
            realized += (1 / 3) * (opt(t2, k, iv) / p0 - 1)
            remaining -= 1 / 3
            stop = entry
        if k - i == 3 and (c - S0) * d <= 0 and remaining > 0.99:
            return opt(c, k, iv) / p0 - 1 - SPREAD, k - i
        if remaining < 0.34:
            trail = df.Low.iloc[k - 2:k + 1].min() if call else df.High.iloc[k - 2:k + 1].max()
            stop = max(stop, trail) if call else min(stop, trail)
    k = min(i + max_days, len(df) - 1)
    iv = df.rv.iat[k] * IV_MULT[call]
    return realized + remaining * (opt(df.Close.iat[k], k, iv) / p0 - 1) - SPREAD, k - i


def run_all(universe, exit_kind, delta):
    rows = []
    for sym, df in universe.items():
        eligible = (df.raw_close < MAX_PRICE) & (df.dvol > MIN_DVOL)
        for name, (lsig, ssig) in setups(df).items():
            for d, sig in ((1, lsig), (-1, ssig)):
                idx = np.where((sig & eligible).values)[0]
                last_exit = -1
                for i in idx:
                    if i <= last_exit or i >= len(df) - 2:
                        continue
                    S0, sigma = df.Close.iat[i], df.rv.iat[i] * IV_MULT[d > 0]
                    scale = df.raw_close.iat[i] / S0     # undo split adjustment: real contract price
                    cost = bs(S0, strike(S0, sigma, d > 0, delta), DTE / 365, sigma, d > 0) * 100 * (1 + SPREAD / 2) * scale
                    r, held = simulate(df, i, d, exit_kind, delta)
                    last_exit = i + held
                    rows.append({"sym": sym, "date": df.index[i], "setup": name, "side": "call" if d > 0 else "put",
                                 "ret": r, "cost": cost, "held": held, "exit_date": df.index[min(i + held, len(df) - 1)]})
    return pd.DataFrame(rows)


def stats(g):
    r = g.ret.values
    return pd.Series({"N": len(r), "win%": round((r > 0).mean() * 100), "avg%": round(r.mean() * 100, 1),
                      "median%": round(np.median(r) * 100, 1),
                      "PF": round(r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9), 2),
                      "avg cost$": round(g.cost.mean()), "days": round(g.held.mean(), 1)})


def account(trades, start=500.0, frac=0.20, max_open=3):
    """$500 cash account: each day, settle, close exits, then open new signals
    (most liquid first) with up to `frac` of equity each, whole contracts."""
    t = trades.sort_values("date")
    cash, pending, open_pos, path = start, [], [], []
    days = sorted(set(t.date) | set(t.exit_date))
    by_day = t.groupby("date")
    for day in days:
        cash += sum(a for d, a in pending if d < day)
        pending = [(d, a) for d, a in pending if d >= day]
        still = []
        for p in open_pos:
            if p["exit_date"] <= day:
                pending.append((day, p["n"] * p["cost"] * (1 + p["ret"])))
            else:
                still.append(p)
        open_pos = still
        equity = cash + sum(a for _, a in pending) + sum(p["n"] * p["cost"] for p in open_pos)
        if day in by_day.groups:
            for _, r in by_day.get_group(day).iterrows():
                if len(open_pos) >= max_open:
                    break
                n = int(min(frac * equity, cash) // r.cost)
                if n < 1:
                    continue
                cash -= n * r.cost
                open_pos.append({"n": n, "cost": r.cost, "ret": r.ret, "exit_date": r.exit_date})
        path.append(equity)
    p = pd.Series(path)
    return p.iloc[-1], (p / p.cummax() - 1).min()


if __name__ == "__main__":
    universe = {}
    for f in sorted(DATA.glob("*.csv")):
        try:
            universe[f.stem] = load(f.stem)
        except Exception as e:
            print(f.stem, "skipped:", e)
    print(f"{len(universe)} symbols; eligible = price < ${MAX_PRICE:.0f} then and 20-day $ volume > ${MIN_DVOL/1e6:.0f}M")
    pd.set_option("display.width", 250)
    for exit_kind, delta in (("carter", 0.70), ("carter", "ATM"), ("bracket", "ATM"), ("holp", 0.70), ("holp", "ATM")):
        if True:
            t = run_all(universe, exit_kind, delta)
            if exit_kind == "holp":
                t = t[t.setup.str.startswith("HOLP")]
            t["year"] = t.date.dt.year
            print(f"\n=== exit: {exit_kind}, option: {'70-delta ITM' if delta == 0.70 else 'ATM'}, 30 DTE, spread {SPREAD:.0%} ===")
            print(t.groupby(["setup", "side"]).apply(stats, include_groups=False).to_string())
            for (setup, side), g in t.groupby(["setup", "side"]):
                g = g.sort_values("date")
                half = len(g) // 2
                yr = g.groupby("year").ret.mean().mul(100).round(0).astype(int).to_dict()
                eq, dd = account(g)
                print(f"  {setup} / {side}: halves {g.ret.iloc[:half].mean():+.1%} / {g.ret.iloc[half:].mean():+.1%};"
                      f" $500 @20% -> ${eq:,.0f} (max DD {dd:.0%}); by year avg%: {yr}")

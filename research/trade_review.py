"""Review a Webull order-history CSV: pair fills into round trips and measure
what actually made or lost money.

CSV columns: order_id,filled_time,place_time,symbol,instrument_type,option_type,
strike,expiry,side,position_intent,qty,price,order_type,combo_type

Options are matched FIFO per contract. Buys never sold are settled at
intrinsic value on expiry (using the underlying's daily close). Each option
entry is also tagged with the daily-chart setup state of its underlying:
EMAs 8/21/34/55/89 stacked + squeeze momentum direction.

Run: python3 research/trade_review.py <trades.csv>   (keep the CSV out of git)
"""
import sys
from collections import defaultdict, deque

import numpy as np
import pandas as pd
import yfinance as yf

from intraday_squeeze import squeeze


def load(path):
    d = pd.read_csv(path, dtype={"order_id": str})
    d = d.drop_duplicates("order_id")
    d["t"] = pd.to_datetime(d.filled_time, utc=True, format="mixed").dt.tz_convert("America/New_York")
    d["expiry"] = pd.to_datetime(d.expiry, errors="coerce")
    return d.sort_values("t").reset_index(drop=True)


def daily_states(symbols, start):
    px = yf.download(sorted(symbols), start=start, auto_adjust=False, progress=False)
    out = {}
    for s in symbols:
        try:
            df = px.xs(s, axis=1, level=1).dropna()
        except KeyError:
            continue
        if len(df) < 100:
            continue
        # Yahoo back-adjusts for splits; undo it so expiry intrinsic uses the
        # prices the contracts actually traded against.
        splits = yf.Ticker(s).splits
        raw = df.Close.copy()
        if len(splits):
            splits.index = splits.index.tz_localize(None)
            for when, ratio in splits.items():
                raw[raw.index < when] *= ratio
        sq = squeeze(df)
        c = df.Close
        e = {n: c.ewm(span=n, adjust=False).mean() for n in (8, 21, 34, 55, 89)}
        bull = (e[8] > e[21]) & (e[21] > e[34]) & (e[34] > e[55]) & (e[55] > e[89])
        bear = (e[8] < e[21]) & (e[21] < e[34]) & (e[34] < e[55]) & (e[55] < e[89])
        st = pd.DataFrame({"close": c, "bull": bull, "bear": bear,
                           "mom_up": sq.mom > 0, "sq_on": sq.on})
        # setup state known at the *prior* close (no lookahead for intraday entries)
        out[s] = st.shift(1).assign(close=raw)
    return out


def round_trips(d, states):
    opt = d[d.instrument_type == "OPTION"]
    books = defaultdict(deque)
    trips = []
    for _, r in opt.iterrows():
        key = (r.symbol, r.option_type, r.strike, r.expiry)
        qty, px = int(r.qty), float(r.price)
        if r.side == "BUY":
            books[key].append([r, qty, px])
            continue
        while qty > 0 and books[key]:
            lot = books[key][0]
            n = min(qty, lot[1])
            trips.append((lot[0], n, lot[2], px, r.t, "sold"))
            lot[1] -= n
            qty -= n
            if lot[1] == 0:
                books[key].popleft()
    for key, lots in books.items():   # held to expiry
        sym, typ, k, exp = key
        st = states.get(sym)
        if exp > pd.Timestamp.now():
            continue
        if st is None:   # no price history (e.g. delisted): assume expired worthless
            intrinsic, how = 0.0, "expired (no data)"
        else:
            close = st.close.asof(exp)
            intrinsic, how = max(0.0, (close - k) if typ == "CALL" else (k - close)), "expired"
        for r, n, px in lots:
            if n > 0:
                trips.append((r, n, px, intrinsic, exp.tz_localize("America/New_York") + pd.Timedelta(hours=16), how))
    rows = []
    for r, n, buy, sell, t_out, how in trips:
        st = states.get(r.symbol)
        s = st.loc[:r.t.tz_localize(None).normalize()].iloc[-1] if st is not None else None
        call = r.option_type == "CALL"
        aligned = None if s is None else bool((s.bull and s.mom_up) if call else (s.bear and not s.mom_up))
        rows.append({
            "entry": r.t, "year": r.t.year, "symbol": r.symbol, "type": r.option_type,
            "dte": (r.expiry.normalize() - r.t.tz_localize(None).normalize()).days,
            "qty": n, "buy": buy, "sell": sell, "pnl": (sell - buy) * 100 * n,
            "ret": sell / buy - 1 if buy else np.nan, "premium": buy * 100 * n,
            "hold_min": (t_out - r.t).total_seconds() / 60, "exit": how,
            "order_type": r.order_type, "setup_aligned": aligned,
        })
    return pd.DataFrame(rows).sort_values("entry")


def table(t, by):
    g = t.groupby(by, dropna=False)
    return pd.DataFrame({
        "trips": g.size(), "win%": g.apply(lambda x: (x.pnl > 0).mean() * 100).round(0),
        "net$": g.pnl.sum().round(0), "avg_win$": g.apply(lambda x: x.pnl[x.pnl > 0].mean()).round(0),
        "avg_loss$": g.apply(lambda x: x.pnl[x.pnl <= 0].mean()).round(0),
        "med_ret%": (g.ret.median() * 100).round(0), "avg_premium$": g.premium.mean().round(0),
    })


if __name__ == "__main__":
    d = load(sys.argv[1])
    syms = set(d[d.instrument_type == "OPTION"].symbol)
    t = round_trips(d, daily_states(syms, str(d.t.min().year - 1) + "-01-01"))
    t["dte_bucket"] = pd.cut(t.dte, [-1, 0, 2, 7, 30, 9999], labels=["0DTE", "1-2", "3-7", "8-30", ">30"])
    t["hold"] = pd.cut(t.hold_min, [-1, 15, 60, 390, 1e9], labels=["<15m", "15-60m", "same day", "overnight+"])
    pd.set_option("display.width", 200)
    print(f"Option round trips: {len(t)}   net ${t.pnl.sum():,.0f}   win {(t.pnl > 0).mean():.0%}\n")
    for by in ("year", "symbol", "type", "dte_bucket", "hold", "exit", "order_type", "setup_aligned"):
        print(table(t, by).to_string(), "\n")
    print("Largest losses:")
    print(t.nsmallest(8, "pnl")[["entry", "symbol", "type", "dte", "qty", "buy", "sell", "pnl", "exit", "hold_min"]].to_string(index=False))
    print("\nLargest wins:")
    print(t.nlargest(8, "pnl")[["entry", "symbol", "type", "dte", "qty", "buy", "sell", "pnl", "exit", "hold_min"]].to_string(index=False))
    eq = t.set_index("entry").pnl.cumsum()
    print("\nCumulative P&L by quarter:")
    print(eq.resample("QE").last().dropna().round(0).to_string())

"""Screen liquid, optionable stocks/ETFs that a ~$500 account can trade:
ATM options a week or two out must cost little enough to fit a small risk
budget, with tight bid/ask spreads and real open interest.

Run: python3 research/small_account_screen.py
"""
import numpy as np
import pandas as pd
import yfinance as yf

CANDIDATES = [
    # ETFs
    "IWM", "XLF", "SLV", "GDX", "EEM", "KRE", "XLE", "TQQQ", "SQQQ", "SOXL", "TLT", "HYG", "UVXY", "ARKK",
    # liquid single names, wide range of prices
    "F", "SOFI", "PLTR", "INTC", "AMD", "NIO", "AAL", "BAC", "T", "PFE", "SNAP", "RIVN", "LCID",
    "HOOD", "UBER", "CCL", "NU", "MARA", "RIOT", "WBD", "GRAB", "CSCO", "KO", "VZ", "C", "WFC",
    "AAPL", "NVDA", "TSLA", "AMZN", "META", "MSFT", "GOOGL", "COIN", "MSTR", "SMCI", "MU", "DKNG",
]


def atm_row(tk, spot, min_dte=5, max_dte=16):
    today = pd.Timestamp.now().normalize()
    exps = [e for e in tk.options if min_dte <= (pd.Timestamp(e) - today).days <= max_dte]
    if not exps:
        return None
    e = exps[0]
    ch = tk.option_chain(e)
    out = {"expiry": e, "dte": (pd.Timestamp(e) - today).days}
    for side, df in (("call", ch.calls), ("put", ch.puts)):
        r = df.iloc[(df.strike - spot).abs().argsort()[:1]].iloc[0]
        mid = (r.bid + r.ask) / 2 if r.ask > 0 else np.nan
        out[f"{side}_cost$"] = round(r.ask * 100, 0)
        out[f"{side}_spread%"] = round((r.ask - r.bid) / mid * 100, 1) if mid else np.nan
        out[f"{side}_oi"] = int(r.openInterest or 0)
    out["opt_vol_day"] = int((ch.calls.volume.fillna(0).sum() + ch.puts.volume.fillna(0).sum()))
    return out


rows = []
for s in CANDIDATES:
    try:
        tk = yf.Ticker(s)
        h = tk.history(period="1mo")
        spot = h.Close.iloc[-1]
        r = atm_row(tk, spot)
        if r is None:
            continue
        rows.append({"symbol": s, "price": round(spot, 2),
                     "avg_$vol_M": round((h.Close * h.Volume).mean() / 1e6, 0), **r})
    except Exception as e:
        print(s, "skipped:", e)

t = pd.DataFrame(rows)
t["max_cost$"] = t[["call_cost$", "put_cost$"]].max(axis=1)
t["max_spread%"] = t[["call_spread%", "put_spread%"]].max(axis=1)
pd.set_option("display.width", 250)
print("All candidates (ATM, first expiry 5-16 days out):")
print(t.sort_values("max_cost$").to_string(index=False))
ok = t[(t["max_cost$"] <= 100) & (t["max_spread%"] <= 10) & (t.call_oi >= 500) & (t.put_oi >= 500)
       & (t["avg_$vol_M"] >= 200)]
print("\nFits a $500 account (ATM <= $100, spread <= 10%, OI >= 500, $200M+/day traded):")
print(ok.sort_values("opt_vol_day", ascending=False).to_string(index=False))

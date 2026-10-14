""""Hit and quit" on 0DTE QQQ/SPY: take the one-strike trade; once a trade
wins, stop for the day. Compared against no daily limit and one-try-per-day.

Uses Webull 5-min bars from data/ when present (else Yahoo's last 60 days),
and the calibrated option pricing in zero_dte_study.

Run: python3 research/hit_and_quit.py
"""
import pandas as pd

import zero_dte_study as z

MORNING = {t for t in (f"{h:02d}:{m:02d}" for h in (9, 10, 11) for m in range(0, 60, 15))
           if "09:45" <= t <= "11:30"}
AFTERNOON = {"15:00", "15:15", "15:30"}
RULES = {"no daily limit": {}, "hit & quit (max 3 tries)": {"quit_on_win": True, "max_per_day": 3},
         "one try per day": {"max_per_day": 1}}


def daily(t):
    return t.groupby("day").pnl.sum()


def summarize(t, **lab):
    d = daily(t)
    eq, dd = z.account_sim(t)
    return {**lab, "trades": len(t), "days": len(d), "win% trades": round((t.pnl > 0).mean() * 100),
            "green days%": round((d > 0).mean() * 100), "avg $/day (1 lot)": round(d.mean(), 1),
            "avg cost$": round(t.cost.mean()), "total $ (1 lot)": round(t.pnl.sum()),
            "$500 @20%/day": round(eq), "max DD": f"{dd:.0%}"}


if __name__ == "__main__":
    data = z.load()
    print("IV multipliers:", z.calibrate())
    span = f"{data['QQQ'].index[0]:%Y-%m-%d} to {data['QQQ'].index[-1]:%Y-%m-%d}"
    rows, keep = [], {}
    for sym, df in data.items():
        for wname, times in (("before lunch", MORNING), ("3:00-3:30pm", AFTERNOON)):
            for how in ("setup", "calls", "puts", "trend (VWAP)"):
                for rname, kw in RULES.items():
                    t = z.one_strike(df, times, how, sym=sym, **kw)
                    if t.empty:
                        continue
                    keep[(sym, wname, how, rname)] = t
                    rows.append(summarize(t, sym=sym, window=wname, direction=how, rule=rname))
    pd.set_option("display.width", 260)
    print(f"\nOne-strike 0DTE (2 OTM, +$1 target / -$1 stop / 60 min), {span}")
    print(pd.DataFrame(rows).to_string(index=False))

    print("\nBy year, QQQ before lunch + setup (avg $/day per 1 contract, green days):")
    for rname in RULES:
        t = keep.get(("QQQ", "before lunch", "setup", rname))
        if t is None:
            continue
        d = daily(t)
        d.index = pd.to_datetime(d.index)
        by = d.groupby(d.index.year).agg(["mean", "count", lambda x: (x > 0).mean()])
        print(f"  {rname}: " + "; ".join(f"{y}: ${r['mean']:+.1f}/day, {int(r['count'])} days, {r['<lambda_0>']:.0%} green"
                                         for y, r in by.iterrows()))

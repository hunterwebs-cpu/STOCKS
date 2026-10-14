"""CLI.

  python -m trader.run replay [--days 59] [--out runs/replay]
  python -m trader.run live   [--out runs/live] [--data yahoo|webull]
  python -m trader.run report [--out runs/live]

Paper only: nothing in this package can place a real order.
"""
import argparse
import json
import time as _time
from pathlib import Path

import pandas as pd

from .broker import PaperBroker
from .config import Config
from .data import NY, source
from .engine import Engine
from .journal import Journal
from .risk import DayState
from .signals import build_signals


def replay(cfg, out, days, data):
    out = Path(out)
    if out.exists():
        for f in out.glob("*.csv"):
            f.unlink()
    j = Journal(out)
    df5 = source(data).bars5(cfg.symbol, days)
    sig = build_signals(df5, cfg)
    eng = Engine(cfg, j)
    for now, bar in sig.iterrows():
        eng.on_bar(now, bar)
    if eng.broker.position:
        last = sig.iloc[-1]
        eng._close(last.Close, sig.index[-1], "end of replay")
    j.flush()
    rep = j.report()
    rep.update({"period": f"{sig.index[0]:%Y-%m-%d} to {sig.index[-1]:%Y-%m-%d}",
                "end_equity": round(eng.broker.equity(sig.Close.iloc[-1]), 2)})
    j.save_json("summary.json", {"config": cfg.to_dict(), "report": rep})
    return rep


def _load_state(path, cfg):
    if not path.exists():
        return None, None, None
    s = json.loads(path.read_text())
    day = DayState(**{**s["day"], "date": pd.Timestamp(s["day"]["date"]).date()}) if s.get("day") else None
    return PaperBroker.from_dict(s["broker"], cfg.slippage_bps), pd.Timestamp(s["last_bar"]), day


def live(cfg, out, data):
    out = Path(out)
    j = Journal(out)
    state = out / "state.json"
    broker, last_bar, day = _load_state(state, cfg)
    eng = Engine(cfg, j, broker)
    if day:
        eng.risk.day = day
    src = source(data)
    print(f"Paper trading {cfg.symbol} from {out}. Ctrl-C to stop.")
    while True:
        now = pd.Timestamp.now(tz=NY)
        if now.weekday() >= 5 or now.time() > pd.Timestamp("16:05").time():
            print("Market closed; exiting.")
            break
        try:
            sig = build_signals(src.bars5(cfg.symbol, 20), cfg)
        except Exception as e:      # data hiccup: keep running, never crash mid-trade
            print(f"{now:%H:%M:%S} data error: {e}")
            _time.sleep(30)
            continue
        new = sig[sig.index > last_bar] if last_bar is not None else sig.iloc[-1:]
        for t, bar in new.iterrows():
            eng.on_bar(t, bar)
            last_bar = t
            pos = eng.broker.position
            print(f"{t:%m-%d %H:%M} close {bar.Close:.2f} equity {eng.broker.equity(bar.Close):.2f}"
                  + (f" | {'LONG' if pos.side > 0 else 'SHORT'} {pos.qty} @ {pos.entry:.2f}" if pos else "")
                  + (" | LONG SETUP" if bar.long_setup else "") + (" | SHORT SETUP" if bar.short_setup else ""))
        if len(new):
            j.flush()
            d = eng.risk.day
            state.write_text(json.dumps({"broker": eng.broker.to_dict(), "last_bar": str(last_bar),
                                         "day": {**d.__dict__, "date": str(d.date)}}, default=str))
        _time.sleep(20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["replay", "live", "report"])
    ap.add_argument("--out", default=None)
    ap.add_argument("--days", type=int, default=59)
    ap.add_argument("--data", default="yahoo", choices=["yahoo", "webull"])
    ap.add_argument("--equity", type=float, default=500.0)
    a = ap.parse_args()
    cfg = Config(start_equity=a.equity)
    out = a.out or f"runs/{a.mode if a.mode != 'report' else 'live'}"
    if a.mode == "replay":
        print(json.dumps(replay(cfg, out, a.days, a.data), indent=2))
    elif a.mode == "live":
        live(cfg, out, a.data)
    else:
        print(json.dumps(Journal(out).report(), indent=2))


if __name__ == "__main__":
    main()

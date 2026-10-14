import json
from pathlib import Path

import pandas as pd


class Journal:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.decisions, self.trades = [], []

    def decision(self, now, side, taken, reasons, price):
        self.decisions.append({"time": str(now), "side": "long" if side > 0 else "short",
                               "taken": taken, "reasons": "; ".join(reasons), "price": round(price, 4)})

    def trade(self, rec):
        self.trades.append({k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in rec.items()})

    def flush(self):
        for name, rows in (("decisions", self.decisions), ("trades", self.trades)):
            f = self.folder / f"{name}.csv"
            new = pd.DataFrame(rows)
            if f.exists() and len(new):
                new = pd.concat([pd.read_csv(f), new])
            if len(new):
                new.to_csv(f, index=False)
        self.decisions, self.trades = [], []

    def report(self) -> dict:
        tf, df = self.folder / "trades.csv", self.folder / "decisions.csv"
        t = pd.read_csv(tf) if tf.exists() else pd.DataFrame()
        d = pd.read_csv(df) if df.exists() else pd.DataFrame()
        out = {"signals": len(d), "taken": int(d.taken.sum()) if len(d) else 0}
        if len(d):
            blocked = d[~d.taken].reasons.str.split("; ").explode().value_counts()
            out["blocked_by"] = blocked.to_dict()
        if len(t):
            out.update({"trades": len(t), "win%": round((t.pnl > 0).mean() * 100, 1),
                        "avg_R": round(t.R.mean(), 3), "total_R": round(t.R.sum(), 2),
                        "net_usd": round(t.pnl.sum(), 2),
                        "exits": t.reason.value_counts().to_dict()})
        return out

    def save_json(self, name, obj):
        (self.folder / name).write_text(json.dumps(obj, indent=2, default=str))

"""Paper broker for a cash account: settled-cash rules (T+1), fractional
shares, and bracket exits evaluated on bar highs/lows. No real orders."""
from dataclasses import dataclass, field

import pandas as pd
from pandas.tseries.offsets import BDay


@dataclass
class Position:
    side: int            # +1 long, -1 short
    qty: float
    entry: float
    stop: float
    target: float
    opened: pd.Timestamp
    risk_usd: float


@dataclass
class PaperBroker:
    cash_settled: float
    slippage_bps: float = 2.0
    pending: list = field(default_factory=list)   # [(settle_date, amount)]
    position: Position | None = None

    def settle(self, now: pd.Timestamp):
        due = [p for p in self.pending if p[0] <= now.normalize()]
        self.pending = [p for p in self.pending if p[0] > now.normalize()]
        self.cash_settled += sum(a for _, a in due)

    @property
    def cash_unsettled(self):
        return sum(a for _, a in self.pending)

    def equity(self, price: float) -> float:
        pos = 0.0
        if self.position:
            p = self.position
            pos = p.qty * p.entry + p.side * p.qty * (price - p.entry)
        return self.cash_settled + self.cash_unsettled + pos

    def _slip(self, px, side, opening):
        s = self.slippage_bps / 1e4
        worse_up = (side > 0) == opening
        return px * (1 + s) if worse_up else px * (1 - s)

    def open(self, side, qty, price, stop, target, now) -> Position:
        fill = self._slip(price, side, True)
        cost = qty * fill
        assert cost <= self.cash_settled + 1e-9, "cash account: insufficient settled cash"
        self.cash_settled -= cost
        self.position = Position(side, qty, fill, stop, target, now, qty * abs(fill - stop))
        return self.position

    def close(self, price, now, reason) -> dict:
        p = self.position
        fill = self._slip(price, p.side, False)
        proceeds = p.qty * p.entry + p.side * p.qty * (fill - p.entry)
        self.pending.append(((now.normalize() + BDay(1)), proceeds))   # T+1
        pnl = proceeds - p.qty * p.entry
        self.position = None
        return {"opened": p.opened, "closed": now, "side": p.side, "qty": round(p.qty, 4),
                "entry": round(p.entry, 4), "exit": round(fill, 4), "stop": round(p.stop, 4),
                "target": round(p.target, 4), "pnl": round(pnl, 4),
                "R": round(pnl / p.risk_usd, 3) if p.risk_usd else 0.0, "reason": reason}

    def check_bracket(self, bar) -> tuple[float, str] | None:
        """Stop/target hit inside this bar? Gaps fill at the open; if both are
        touched in one bar, assume the stop (pessimistic)."""
        p = self.position
        if p is None:
            return None
        if p.side > 0:
            if bar.Open <= p.stop:
                return bar.Open, "stop (gap)"
            if bar.Open >= p.target:
                return bar.Open, "target (gap)"
            if bar.Low <= p.stop:
                return p.stop, "stop"
            if bar.High >= p.target:
                return p.target, "target"
        else:
            if bar.Open >= p.stop:
                return bar.Open, "stop (gap)"
            if bar.Open <= p.target:
                return bar.Open, "target (gap)"
            if bar.High >= p.stop:
                return p.stop, "stop"
            if bar.Low <= p.target:
                return p.target, "target"
        return None

    def to_dict(self):
        return {"cash_settled": self.cash_settled,
                "pending": [(str(d.date()), a) for d, a in self.pending],
                "position": None if not self.position else {
                    **self.position.__dict__, "opened": str(self.position.opened)}}

    @classmethod
    def from_dict(cls, d, slippage_bps):
        b = cls(d["cash_settled"], slippage_bps,
                [(pd.Timestamp(x), a) for x, a in d["pending"]])
        if d["position"]:
            p = dict(d["position"])
            p["opened"] = pd.Timestamp(p["opened"])
            b.position = Position(**p)
        return b

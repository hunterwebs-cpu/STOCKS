"""Hard risk rules. Every entry must pass every rule; the reasons a signal
was blocked are journaled so the discipline report can show them."""
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class DayState:
    date: object = None
    start_equity: float = 0.0
    trades: int = 0
    realized: float = 0.0
    consecutive_losses: int = 0


@dataclass
class RiskGate:
    cfg: object
    day: DayState = field(default_factory=DayState)

    def new_bar(self, now: pd.Timestamp, equity: float):
        if self.day.date != now.date():
            self.day = DayState(now.date(), equity)

    def record_close(self, pnl: float):
        self.day.realized += pnl
        self.day.consecutive_losses = self.day.consecutive_losses + 1 if pnl <= 0 else 0

    def check(self, side: int, now: pd.Timestamp, broker, price: float, atr: float):
        c, d = self.cfg, self.day
        reasons = []
        t = now.time()
        open_min = (now - now.normalize()).total_seconds() / 60 - (9 * 60 + 30)
        if side < 0 and not c.allow_short:
            reasons.append("short not allowed (cash account)")
        if broker.position is not None:
            reasons.append("position already open (no adding)")
        if open_min < c.no_entry_first_min:
            reasons.append("too early after open")
        if t > c.last_entry:
            reasons.append("too late in session")
        if d.trades >= c.max_trades_per_day:
            reasons.append("max trades for the day")
        if d.realized <= -c.daily_loss_limit * d.start_equity:
            reasons.append("daily loss limit hit")
        if d.consecutive_losses >= c.max_consecutive_losses:
            reasons.append("cooldown after consecutive losses")
        if not atr or atr != atr or atr <= 0:
            reasons.append("no ATR yet")
        qty = 0.0
        if not reasons:
            stop_dist = c.stop_atr * atr
            equity = broker.equity(price)
            qty_risk = c.risk_per_trade * equity / stop_dist
            qty_cash = broker.cash_settled * 0.99 / price
            qty = round(min(qty_risk, qty_cash), 4)
            if qty * price < c.min_order_usd:
                reasons.append("settled cash below minimum order")
        return (not reasons), reasons, qty

"""One code path for replay and live: feed completed 10-min bars in order."""
import pandas as pd

from .broker import PaperBroker
from .risk import RiskGate


class Engine:
    def __init__(self, cfg, journal, broker: PaperBroker | None = None):
        self.cfg, self.journal = cfg, journal
        self.broker = broker or PaperBroker(cfg.start_equity, cfg.slippage_bps)
        self.risk = RiskGate(cfg)

    def _close(self, price, now, reason):
        rec = self.broker.close(price, now, reason)
        self.risk.record_close(rec["pnl"])
        self.journal.trade(rec)

    def on_bar(self, now: pd.Timestamp, bar):
        c, b = self.cfg, self.broker
        b.settle(now)
        self.risk.new_bar(now, b.equity(bar.Close))

        # 1) manage an open position (bracket first, then rule exits at the close)
        if b.position is not None and b.position.opened < now:
            hit = b.check_bracket(bar)
            if hit:
                self._close(hit[0], now, hit[1])
            else:
                p = b.position
                held = (now - p.opened).total_seconds() / 60
                opposite = (bar.Close < bar.Open) if p.side > 0 else (bar.Close > bar.Open)
                if now.time() >= c.flatten_at:
                    self._close(bar.Close, now, "flatten before close")
                elif held >= c.time_stop_min:
                    self._close(bar.Close, now, "time stop")
                elif c.exit_on_opposite_candle and opposite:
                    self._close(bar.Close, now, "opposite candle")

        # 2) entries
        for side, flag in ((1, bar.long_setup), (-1, bar.short_setup)):
            if not flag:
                continue
            ok, reasons, qty = self.risk.check(side, now, b, bar.Close, bar.atr)
            self.journal.decision(now, side, ok, reasons, bar.Close)
            if ok:
                stop = bar.Close - side * c.stop_atr * bar.atr
                target = bar.Close + side * c.target_atr * bar.atr
                b.open(side, qty, bar.Close, stop, target, now)
                self.risk.day.trades += 1

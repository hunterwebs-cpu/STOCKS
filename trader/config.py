from dataclasses import dataclass, asdict
from datetime import time


@dataclass
class Config:
    symbol: str = "QQQ"
    start_equity: float = 500.0

    # Setup: 10-min trigger, 60-min filter (EMAs 8/21/34/55/89 + squeeze momentum)
    ema_lengths: tuple = (8, 21, 34, 55, 89)
    squeeze_len: int = 20
    atr_len: int = 14

    # Exits (on the underlying)
    stop_atr: float = 1.0           # bracket stop distance, in 10-min ATRs
    target_atr: float = 2.0         # bracket target distance
    time_stop_min: int = 60         # from the user's own history: 15-60 min holds were the only winners
    exit_on_opposite_candle: bool = True

    # Risk rules (enforced by RiskGate, never by the signal code)
    risk_per_trade: float = 0.01    # fraction of equity lost if the stop is hit
    max_trades_per_day: int = 3
    daily_loss_limit: float = 0.03  # stop trading for the day after losing this fraction
    max_consecutive_losses: int = 2 # cooldown: no more entries that day
    no_entry_first_min: int = 15
    last_entry: time = time(15, 0)
    flatten_at: time = time(15, 50)
    allow_short: bool = False       # cash account: shares cannot be shorted
    min_order_usd: float = 5.0      # Webull fractional-share minimum

    slippage_bps: float = 2.0

    def to_dict(self):
        d = asdict(self)
        d["last_entry"], d["flatten_at"] = str(self.last_entry), str(self.flatten_at)
        return d

import numpy as np
import pandas as pd
import pytest

from trader.broker import PaperBroker
from trader.config import Config
from trader.indicators import linreg_end
from trader.risk import RiskGate
from trader.signals import build_signals

NY = "America/New_York"


def synthetic_5m(days=40, seed=1):
    rng = np.random.default_rng(seed)
    idx = []
    for d in pd.bdate_range("2026-01-05", periods=days):
        idx += list(pd.date_range(d + pd.Timedelta("9h30min"), d + pd.Timedelta("15h55min"), freq="5min"))
    idx = pd.DatetimeIndex(idx).tz_localize(NY)
    c = 500 + np.cumsum(rng.normal(0, 0.4, len(idx)))
    o = np.r_[c[0], c[:-1]]
    hi = np.maximum(o, c) + rng.uniform(0, .3, len(c))
    lo = np.minimum(o, c) - rng.uniform(0, .3, len(c))
    return pd.DataFrame({"Open": o, "High": hi, "Low": lo, "Close": c}, index=idx)


def test_linreg_matches_polyfit():
    s = pd.Series(np.random.default_rng(0).normal(size=60))
    got = linreg_end(s, 20)
    for i in (19, 33, 59):
        y = s.iloc[i - 19:i + 1].to_numpy()
        want = np.polyval(np.polyfit(np.arange(20), y, 1), 19)
        assert got.iloc[i] == pytest.approx(want)


def test_signals_have_no_lookahead():
    cfg, df = Config(), synthetic_5m()
    full = build_signals(df, cfg)
    cut = df.index[len(df) * 2 // 3]
    part = build_signals(df[df.index < cut], cfg)
    common = part.index[:-1]          # last partial 10/60-min bar may legitimately differ
    cols = ["long_setup", "short_setup", "htf_long", "htf_short"]
    pd.testing.assert_frame_equal(full.loc[common, cols], part.loc[common, cols])


def test_cash_account_settles_next_business_day():
    b = PaperBroker(500.0, slippage_bps=0)
    t = pd.Timestamp("2026-01-09 10:00", tz=NY)        # Friday
    b.open(1, 1.0, 400.0, 398.0, 404.0, t)
    b.close(401.0, t + pd.Timedelta(minutes=30), "test")
    assert b.cash_settled == pytest.approx(100.0)
    b.settle(pd.Timestamp("2026-01-10 10:00", tz=NY))  # Saturday: not yet
    assert b.cash_settled == pytest.approx(100.0)
    b.settle(pd.Timestamp("2026-01-12 09:30", tz=NY))  # Monday
    assert b.cash_settled == pytest.approx(501.0)


def test_cannot_spend_unsettled_cash():
    b = PaperBroker(100.0, slippage_bps=0)
    with pytest.raises(AssertionError):
        b.open(1, 1.0, 400.0, 398.0, 404.0, pd.Timestamp("2026-01-09 10:00", tz=NY))


def test_bracket_assumes_stop_when_both_hit():
    b = PaperBroker(500.0, slippage_bps=0)
    b.open(1, 1.0, 400.0, 398.0, 402.0, pd.Timestamp("2026-01-09 10:00", tz=NY))
    bar = pd.Series({"Open": 400.0, "High": 403.0, "Low": 397.0, "Close": 401.0})
    assert b.check_bracket(bar) == (398.0, "stop")


def test_risk_gate_rules():
    cfg = Config()
    g, b = RiskGate(cfg), PaperBroker(500.0)
    now = pd.Timestamp("2026-01-09 11:00", tz=NY)
    g.new_bar(now, 500.0)
    ok, reasons, qty = g.check(1, now, b, 400.0, 1.5)
    assert ok and 0 < qty * 400 <= 500
    ok, reasons, _ = g.check(-1, now, b, 400.0, 1.5)
    assert "short not allowed (cash account)" in reasons
    b.open(1, qty, 400.0, 398.5, 403.0, now)
    assert "position already open (no adding)" in g.check(1, now, b, 400.0, 1.5)[1]
    g2 = RiskGate(cfg)
    g2.new_bar(now, 500.0)
    g2.record_close(-8.0); g2.record_close(-8.0)   # -16 > 3% of 500
    r = g2.check(1, now, PaperBroker(500.0), 400.0, 1.5)[1]
    assert "cooldown after consecutive losses" in r and "daily loss limit hit" in r
    assert "too early after open" in g2.check(1, pd.Timestamp("2026-01-09 09:40", tz=NY), PaperBroker(500.0), 400.0, 1.5)[1]


def test_state_round_trip():
    b = PaperBroker(500.0, slippage_bps=0)
    t = pd.Timestamp("2026-01-09 10:00", tz=NY)
    b.open(1, 0.5, 400.0, 398.0, 404.0, t)
    b.pending.append((pd.Timestamp("2026-01-12"), 50.0))
    b2 = PaperBroker.from_dict(b.to_dict(), 0)
    assert b2.cash_settled == b.cash_settled and b2.position.qty == 0.5
    assert b2.cash_unsettled == 50.0 and b2.position.opened == t

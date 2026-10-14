# Agentic trader — R&D findings #1 (2026-10-14)

## 1. Existing skills survey

No day-trading skill anywhere has a real body of user reviews. GitHub has no
rating system (stars are bookmarks). Marketplaces with ratings (Agensi) show
one review per skill at most. The issue tracker of the most popular repo
(tradermonty/claude-trading-skills) is filed almost entirely by its own author,
so it is a dev log, not user feedback.

Worth reusing:

| Source | Use it for |
|---|---|
| `webull-inc/webull-openapi-skills` (official) | Broker plumbing: quotes, bars, ticks, depth, options chains, OCO/OTOCO orders, UAT sandbox, per-order notional/qty limits, symbol whitelist. This session also has the Webull MCP connected directly. |
| `tradermonty/claude-trading-skills` (MIT, ~3k stars) | Process scaffolding: `backtest-expert` (robustness methodology), `drawdown-circuit-breaker`, `pre-trade-discipline-gate`, `position-sizer`, `trader-memory-core` (journaling). None of it is intraday or Webull-specific. |

Nothing found implements Simpler Trading / *Mastering the Trade* setups as a
tested system.

## 2. Baseline numbers (2000-01 → 2026-10, daily, dividends included)

Run with `python3 research/baseline_study.py`. Costs are 2 bps per side.

| Strategy | CAGR | Max DD | Sharpe | Years ≥ 30% |
|---|---|---|---|---|
| SPY buy & hold | 8.3% | -55% | 0.51 | 2 / 26 |
| QQQ buy & hold | 8.6% | -83% | 0.44 | 7 / 26 |
| SPY TTM Squeeze, long only | 0.2% | -20% | 0.07 | 0 / 26 |
| QQQ TTM Squeeze, long only | -2.0% | -50% | -0.32 | 0 / 26 |
| SPY 2x daily leverage | 10.9% | -87% | 0.46 | 9 / 26 |
| QQQ 3x daily leverage | -0.5% | -100% | 0.40 | 15 / 26 |

Squeeze, long only, on 8 of today's mega-cap options names (518 trades): win
rate 48%, mean trade +1.25%, median trade -0.34%. That universe is chosen with
hindsight (survivorship bias), so treat it as an upper bound, not an edge.

Caveats: 2000 is an unfavorable start date for buy & hold. The squeeze here is
one mechanical reading of Carter's rules: daily bars, enter on the fire with
momentum confirming, exit after two bars of momentum fading. It has no trend
filter, no multi-timeframe confirmation and no options. It shows that the raw
signal is not an edge on index ETFs. It does not rule out the setups with
filters.

## 3. What this says about the 30%/yr target

* Leverage alone doesn't get there. 2x–3x SPY/QQQ produces many 30%+ years
  but a lower or similar CAGR, with drawdowns of -87% to -100%. Volatility drag
  eats the gains.
* A sustained 30% CAGR would put the system near the very top of professional
  funds. It requires a real edge (Sharpe well above 1) **plus** leverage, or
  small size in inefficient corners. SPY/QQQ are the most efficient
  instruments in the world.
* Proposed working targets: out-of-sample Sharpe > 1.0, max drawdown < 20%,
  and beating SPY buy & hold after costs and taxes. Once something clears
  that, size it up (options or leverage) to reach the return you want, at a
  drawdown you choose deliberately.

## 4. Proposed architecture

```
data  ──>  signals (deterministic Python, backtestable)
                 │
                 v
agent (LLM): regime read, calendar/news veto, trade plan, journal, review
                 │
                 v
risk gate (hard-coded, outside the LLM): size, daily loss stop, max positions,
           PDT count, no undefined-risk options
                 │
                 v
execution: Webull UAT sandbox -> paper -> small live
```

The LLM does not pick entries. Its decisions can't be backtested or
reproduced, so every entry/exit rule lives in code where it can be tested.
The agent handles judgment calls around the rules: earnings and FOMC days,
regime, and whether conditions match what the backtest assumed. It also
handles the journaling and post-mortems that tradermonty's skills already
structure well.

## 5. Next experiments (in order)

1. **Swing, daily:** squeeze plus Simpler-style filters (stacked 8/21/34 EMAs,
   price > 200 SMA, weekly squeeze agreement). Walk-forward, with parameter
   sensitivity plotted rather than optimized.
2. **Universe without hindsight:** rebuild the "high options volume" list
   point-in-time (e.g. top-N by dollar volume each year), not today's winners.
3. **Intraday SPY/QQQ:** opening-range breakout, VWAP reclaim, squeeze on
   5-minute/15-minute bars. Needs years of intraday history. Yahoo gives ~60
   days. Check whether Webull bars go deeper, or budget for Polygon/Databento.
4. **Options expression:** shares vs. ATM calls vs. debit spreads on the same
   signals. Needs historical IV/chains; Black-Scholes with realized-vol proxy
   is a first pass only.
5. **Agent loop in UAT:** wire the surviving rule set to the Webull sandbox
   with the risk gate and journaling.

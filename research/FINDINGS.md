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

---

# Findings #2: options bracket (+30% target / −60% stop per contract)

Clarified goal: buy ATM calls or puts on SPY/QQQ. Sell at +30% of premium,
stop at −60%. Run with `python3 research/options_bracket_study.py`.

**The math:** break-even win rate = 60 / (30 + 60) = **66.7%** before costs,
about 68–70% after the spread. The target sits half as far away as the stop,
so a coin-flip entry already hits the target first about 2/3 of the time.
Time decay (theta) and the premium baked into implied vol then make the
no-edge version lose. A high win rate on this structure proves nothing on its
own.

**Results** (2005–2026, 30 DTE ATM, priced with Black-Scholes using VIX/VXN,
10-day time stop, 1.5% round-trip cost, 5% of account in premium per trade):

| Entry | Trades | Win% | Avg/trade | Account | Max DD |
|---|---|---|---|---|---|
| SPY coin-flip call/put | 868 | 55.8% | −7.4% | 0.03x | −97% |
| SPY calls only, random | 816 | 59.4% | −2.8% | 0.26x | −77% |
| SPY trend pullback (8/21/34 stacked + 21 EMA touch) | 250 | 56.8% | −5.7% | 0.46x | −60% |
| QQQ coin-flip call/put | 977 | 59.0% | −5.8% | 0.05x | −97% |
| QQQ calls only, random | 905 | 62.8% | −0.8% | 0.56x | −60% |
| QQQ trend pullback | 247 | 63.6% | −1.6% | 0.78x | −38% |

Sweep of target/stop pairs on the pullback signal (+30/−30, +50/−50,
+60/−30, +100/−50): all negative. Exits shape the payoff; they cannot
create an edge.

Takeaways:
* No variant reached the ~68% win rate needed. Best was 63.6%.
* Puts lose more than calls. Implied vol usually prices in more movement than
  actually happens, and indexes drift up; long puts pay for both.
* Stops get skipped: 13–88 trades per row gapped through −60% and lost more.
* The trend filters did not clearly beat buying calls at random on QQQ. Any
  "edge" so far is just the market's upward drift.

Limits: modeled prices, not real chain data (no skew, no real fills).
Daily bars only, so 0DTE/intraday day trading is untested. Verdict needs
real historical option data (ThetaData, ORATS, Polygon) before it's final,
but a model this generous to the buyer still losing is a strong signal.

Directions worth testing next:
1. Entries with genuine edge, measured on the underlying first: does the
   signal move price ≥ X% in N days more than 68% of the time?
2. Intraday SPY/QQQ setups with real intraday + option data.
3. The other side of the trade: defined-risk credit spreads. The vol premium
   that hurts buyers here pays sellers, and that structure naturally has
   high win rates.

---

# Findings #3: setup lab, i.e. which setups are actually high-probability

`python3 research/setup_lab.py`. For each setup: how often does the
underlying reach +1 ATR before −2 ATR within 5 days (roughly the
+30%/−60% option bracket)? Compared against the base rate for the same
direction on every bar. **Lift over base is the edge.** The raw hit rate is
mostly set by where the target and stop sit.

| Setup (2000–2026) | SPY hit / base / lift | QQQ hit / base / lift |
|---|---|---|
| RSI(2) < 10, above 200 SMA (long) | 70% / 52% / **+17.7pt** | 62% / 54% / +8.4pt |
| 3 down days, above 200 SMA (long) | 70% / 52% / **+17.5pt** | 62% / 54% / +8.6pt |
| 21 EMA pullback, stacked 8/21/34 (long) | 56% / 52% / +3.4pt | 58% / 54% / +4.0pt |
| TTM squeeze fire, momentum up (long) | 42% / 52% / **−10.8pt** | 43% / 54% / −11.1pt |
| Squeeze fire up + stacked EMAs | 40% / 52% / −12.7pt | 49% / 54% / −4.4pt |
| Short-side setups (below 200 SMA) | mostly ≤ base | mostly ≤ base |

* Buying short-term dips in an uptrend is a real, stable edge on SPY. It
  holds in both halves of the sample (67%→72%, 68%→71%).
* The daily TTM squeeze fire, coded mechanically, is **worse than random**
  for longs. It may still work with Carter's discretion or on intraday
  timeframes, but that has to be shown, not assumed.
* Shorts fight the index's upward drift. Puts need a much stronger reason.

**Opening gap fills (same session)**: small gaps (0.1–0.25%) fill 77–84% of
the time; gaps > 1% fill only 29–40%. Caveat: small gaps fill often *because
the target is tiny*. This is the same trap as the bracket, and it needs a
stop and payoff test before it counts as an edge.

### Does the dip edge survive being traded with options?

Long ATM 30-DTE calls on the two dip signals, same pricing model as #2:

| Bracket | SPY RSI2 | SPY 3-down | QQQ RSI2 | QQQ 3-down |
|---|---|---|---|---|
| +30/−60 | 65% win, +0.8%/trade | 64%, −0.6% | 62%, −2.5% | 68%, +1.9% |
| +30/−30 | 51%, −1.4% | 51%, −1.0% | 51%, −0.7% | 52%, +0.2% |
| +50/−50 | 50%, −3.6% | 48%, −4.6% | 51%, +0.5% | 51%, +1.1% |

The underlying edge is real, but **buying calls roughly breaks even**.
Dips are exactly when implied vol is elevated, so the calls are expensive
and theta plus vol crush eat the edge. That points at the vehicle, not the
setup: express dip-buys by **selling** premium (cash-secured puts or put
credit spreads, where elevated IV is paid to you) or with shares.

---

# Findings #4: Simpler's documented rules, and the user's own QQQ setup

## Constraints (confirmed via Webull, read-only)
* One **individual cash account**. The AI connection has *Trading* authorization.
* Options level 1–2, no margin: **no spreads**. Cash-secured puts on QQQ/SPY
  need ~$73k–77k cash per contract, so selling premium is effectively out.
  The vehicle is long calls/puts (loss capped at premium) or shares.
* Cash account: no PDT rule, but trades must use **settled** funds (options
  settle T+1); reusing unsettled proceeds risks good-faith violations.

## What Simpler / Carter actually document (research agent, public sources)
* Indicator: BB(20, 2) inside KC(20 SMA ± 1.5×ATR20) = squeeze on; momentum =
  linreg(close − avg(Donchian mid, SMA20), 20). thinkorswim's exact formula is
  unpublished. Histogram colors: light blue = >0 rising, dark blue = >0
  falling, red = <0 falling, yellow = <0 rising.
* Entry: first non-squeeze bar after ≥3–5 squeeze bars (sources differ), in
  the histogram's direction. Carter also scales in *during* the squeeze on
  pullbacks to the 8/21 EMA, near 52-week highs, price above the 21/34 EMA,
  EMAs 8/21/34/55/89 stacked.
* Exits: two bars of the fading color (some sources say one). Moves typically
  last 8–10 bars. Daily options plan: stop 2×ATR(21) on the underlying, 3-day
  time stop, scale out 1/3 at prior highs, 1/3 at the 1.272 Fib extension,
  trail the rest.
* Timeframes: Carter's favorites are **daily and 30-min**, plus 195/78/39-min.
  10-min and 60-min are not documented Simpler timeframes.
* Options: ITM, **delta ≥ 0.70**, ≥ 5 days to expiry; stops and targets set on
  the underlying, not on option %.
* Performance: "about 25% of squeezes fail" (promotional, no method given).
  No audited backtests exist. Community backtests show ~52–55% wins and a
  profit factor of ~1.1.

## The user's setup, coded (`research/qqq_stack_squeeze.py`)
QQQ, EMAs 8>21>34>55>89 stacked + histogram light blue → long until the first
red candle (mirror image for shorts). Options modeled as Carter's 70-delta
ITM (30 DTE daily, 7 DTE intraday).

| TF | Variant | N | Win% | Option avg | Median | ≥ +30% |
|---|---|---|---|---|---|---|
| daily (2001–) | long, exit first red candle | 277 | 49% | +0.3% | −2.9% | 7% |
| daily | long, two-bar fade exit | 222 | 48% | +2.9% | −8.3% | 24% |
| daily | long + squeeze fire, first red | 39 | 56% | +4.7% | −0.4% | 13% |
| daily | short, any exit | 74–91 | 30–34% | −3.5% to −15% | — | — |
| 60m (3 yrs) | long, first red | 174 | 32% | −3.2% | −3.8% | 2% |
| 60m | long + fire, first red | 20 | 35% | +7.0% | −2.8% | 15% |
| 10m (60 days) | all variants | 10–48 | 29–50% | about 0 | — | 0–3% |

Takeaways:
* Mechanically, the setup is about **breakeven on longs and a loser on
  shorts**, on every timeframe tested. Nothing approaches a 30% average.
* "Exit on the first red candle" always eats that red candle and cuts
  winners short. Average holds are ~2 bars. The two-bar fade lets winners run
  (24% of daily trades reach +30% on the option) but gives back more on
  losers.
* The one interesting cell (daily long + squeeze fire) has only 39 trades.
  It needs out-of-sample confirmation before anyone believes it.
* Whatever made it work when traded by hand (discretion, the 2020–21 bull
  market, or luck) is not captured by these rules. The user's own Webull
  order history from that period is the best evidence for which.

---

# Findings #5: small accounts ($500): which symbols, which vehicle

**Settlement:** US standard is still **T+1** (since May 28, 2024). An SEC
*petition* (July 2026, Release 4-912) asks for same-day settlement; nothing
adopted. In a cash account you can buy with unsettled funds, but selling that
position before the funds settle is a good-faith violation, so each day's
round trips are limited to settled cash. The paper broker models this.

**Screen** (`research/small_account_screen.py`, ATM options 5–16 DTE): only
**SOFI** (~$14, ATM ~$34–58, spread 3.5–6%, 84k contracts/day) and **F**
(~$12, ATM ~$21–28, spread 7–10%) pass every filter: ATM ≤ $100, spread
≤ 10%, OI ≥ 500, $200M+/day traded. Near misses: AAL (thin call OI), TQQQ /
SQQQ / SMCI (~$130–180 per ATM contract). Quotes were taken after hours, so
re-check spreads intraday.

**User's setup on 60-min bars, ~2 years** (underlying only, R = move ÷ ATR):

| Symbol | Long, exit first red | Halves (avg R) |
|---|---|---|
| SOFI | N 126, win 44%, +0.16R, PF 1.50 | +0.30 / +0.04 |
| F | N 119, win 42%, +0.15R, PF 1.53 | −0.01 / +0.31 |
| QQQ | N 174, win 34%, −0.11R, PF 0.77 | — |
| AAL, TQQQ, SMCI, SQQQ | roughly breakeven or negative | — |

Better than QQQ, but each is good in only one half, and with 28 variants
tested a few were bound to look good. Treat it as a lead, not an edge.

**Vehicle math:** the average trade moves SOFI **$0.027/share** and F
**$0.019/share** over ~2 hours. An ATM option (delta ~0.5) captures about
half of that, $1–1.30 per contract, while the bid/ask spread costs about $2
per contract. **Options lose on this hold length even if the edge is real.**
Fractional shares (commission-free) keep the whole move. For options to work
in a small account the expected move must be large relative to the spread,
which points to swing holds on the daily chart, not 1–2 hour holds.

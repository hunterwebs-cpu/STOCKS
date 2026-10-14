# Paper trader v1: QQQ stack + TTM Squeeze

Paper only. Nothing in `trader/` can send an order to Webull.

## The setup (the user's, coded)
* **Filter (60-min):** EMAs 8 > 21 > 34 > 55 > 89 stacked, squeeze momentum
  light blue (> 0 and rising). Mirror image for bearish.
* **Trigger (10-min):** same stack + light-blue momentum, on the first bar
  it turns on.
* **Exits (on QQQ itself):** bracket stop 1×ATR(10-min), target 2×ATR,
  first opposite-color candle, 60-minute time stop, flat by 15:50.

## Risk rules (`risk.py`, all enforced in code)
| Rule | Default | Why |
|---|---|---|
| No setup, no trade | — | Trades outside the setup lost money in the user's history |
| Never add to an open position | — | Jan 27, 2025 |
| Risk per trade | 1% of equity | Size never grows on a hot streak |
| Max trades per day | 3 | |
| Daily loss limit | 3% | |
| Cooldown after 2 straight losses | rest of day | |
| No entries first 15 min / after 15:00 | | |
| Long only | | Cash account can't short shares; bearish signals are logged |
| Settled cash only (T+1) | | Cash-account rule; avoids good-faith violations |

Every signal is journaled with whether it was taken and, if not, which rule
blocked it (`decisions.csv`). Closed trades are in `trades.csv` with the
result in R (multiples of the amount risked).

## With $500
QQQ options don't fit the rules at $500, so v1 trades **fractional QQQ
shares**. Because each trade uses the settled cash and proceeds settle T+1,
expect at most about one trade per day. The point of this stage is to
measure the setup (avg R, win rate) and the rule-following, not to make
money. Options come after the setup proves out.

## Run
```bash
pip install -r requirements.txt
python -m trader.run replay            # last ~59 days of 5-min data from Yahoo
python -m trader.run live              # during market hours; resumes from runs/live/state.json
python -m trader.run report            # stats + which rules blocked which signals
python -m pytest -q tests
```
`live` checks for a new completed 10-min bar every 20 seconds and exits after
the close. Run it on a computer that stays on during market hours. Start it
each trading morning, e.g. with cron or Task Scheduler. Your own connection
dropping can't hurt a paper account, which is exactly why live money will
need broker-side bracket orders.

`--data webull` uses the Webull OpenAPI (needs `WEBULL_APP_KEY` /
`WEBULL_APP_SECRET`). That adapter is untested until keys exist.

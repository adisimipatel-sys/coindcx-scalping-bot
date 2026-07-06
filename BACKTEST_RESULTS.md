# Backtest Results — Triple-Confirmation Trend Rider

Run date: 2026-07-06
Engine: `backtest.py` — uses the **exact same** `strategy.py` code as the live bot.
Data: **real market data** bundled with the `backtesting` PyPI package
(direct exchange APIs were not reachable from the test environment).

Simulation assumptions (deliberately pessimistic):
- Signals only on closed candles (no lookahead)
- If SL and TP both touch inside one bar, **SL is assumed to hit first**
- Fees/spread charged both sides: forex 0.01%/side (~1 pip), stock/crypto-style 0.2%/side
- Position sizing identical to the bot: 1% equity risk per trade, 25% notional cap

## EURUSD 1h — real forex data, Apr 2017 – Feb 2018 (long + short)

| Metric | Value |
|---|---|
| Bars tested | 2,600 (~5 months) |
| Trades | 43 (16 W / 27 L) |
| Win rate | 37.2% |
| Profit factor | **1.25** |
| Avg R per trade | **+0.17R** |
| Net return | +0.28% (at 1% risk/trade) |
| Max drawdown | 0.23% |
| Exits | SL ×20, TP ×16, Trailing ×7 |

## GOOG 1d — real data 2004–2013, long-only (crypto-spot style regime)

| Metric | Value |
|---|---|
| Bars tested | 1,148 (~4.5 years) |
| Trades | 19 (6 W / 13 L) |
| Win rate | 31.6% |
| Profit factor | **1.34** |
| Avg R per trade | **+0.19R** |
| Net return | +2.16% (buy & hold: +62.9%) |
| Max drawdown | 3.37% |
| Exits | SL ×6, TP ×6, Trailing ×7 |

## Honest interpretation

**Good:**
- Positive expectancy on both real datasets despite pessimistic fills and fees
- Win rate ~35% is *expected and fine* for a 1:2 RR system — losers are small, winners are 2x+
- Drawdowns are tiny — the 1%-risk sizing and ATR stops are doing their job
- Trailing stop captured 7 extended winners in each dataset

**Limitations — read this:**
- Small sample sizes (43 and 19 trades). Not statistically conclusive.
- One time period each. Different market regimes will differ.
- Returns are modest by design: at 1% risk and +0.17R/trade expectancy,
  the system earns roughly +0.17% of account per trade taken.
  It will NOT double your money quickly — nothing legitimate does.
- In a strong bull market a long-only strict-filter system badly lags buy & hold
  (GOOG: +2.2% vs +62.9%). Its value is the tiny drawdown, not max profit.
- Gaps through the stop are filled AT the stop in simulation; real gaps can be worse.

## Run it yourself

```bash
pip install backtesting          # for bundled real sample data
python backtest.py --sample      # offline backtest (what produced this report)
python backtest.py               # backtest YOUR watchlists on live CoinDCX/Yahoo
                                 # data (run at home; data APIs must be reachable)
```

---

# Strategy Comparison (Round 2) — 7 strategies, train/validation split

Run date: 2026-07-06, engine: `strategy_lab.py`.
Data split: first 65% = "train" (where you'd pick a strategy), last 35% =
"valid" (unseen data — the number that actually matters).

## EURUSD 1h (forex, long+short)

| variant | set | trades | win% | PF | avgR | net% | maxDD% |
|---|---|---|---|---|---|---|---|
| trend_rider | train | 24 | 41.7 | 1.52 | +0.23 | +0.27 | 0.23 |
| trend_rider | valid | 19 | 31.6 | 0.76 | -0.09 | -0.15 | 0.21 |
| trend_rr1 | train | 24 | 58.3 | 1.10 | +0.02 | +0.05 | 0.23 |
| trend_rr1 | valid | 19 | 47.4 | 0.75 | -0.15 | -0.15 | 0.21 |
| rsi2_dip | train | 71 | 67.6 | 0.62 | -0.12 | -0.76 | 0.88 |
| rsi2_dip | valid | 41 | **82.9** | **1.92** | +0.10 | +0.51 | 0.21 |
| rsi2_connors | train | 79 | 60.8 | 0.77 | -0.04 | -0.34 | 0.58 |
| rsi2_connors | valid | 44 | 63.6 | 1.04 | -0.02 | +0.03 | 0.23 |
| rsi2_tight | train | 68 | 57.4 | 0.79 | -0.08 | -0.45 | 0.67 |
| rsi2_tight | valid | 40 | 62.5 | 1.11 | +0.01 | +0.11 | 0.22 |
| ema_pullback | train | 63 | 42.9 | 0.61 | -0.26 | -0.70 | 0.78 |
| ema_pullback | valid | 31 | 48.4 | 0.83 | -0.12 | -0.17 | 0.40 |
| bb_reversion | train | 38 | 44.7 | 0.50 | -0.30 | -0.73 | 0.77 |
| bb_reversion | valid | 17 | 47.1 | 0.57 | -0.25 | -0.29 | 0.29 |

## GOOG 1d (long-only, crypto-spot style)

| variant | set | trades | win% | PF | avgR | net% | maxDD% |
|---|---|---|---|---|---|---|---|
| trend_rider | train | 10 | 10.0 | 0.35 | -0.23 | -2.33 | 3.31 |
| trend_rider | valid | 9 | 55.6 | **2.61** | +0.65 | +4.60 | 1.62 |
| trend_rr1 | train | 10 | 70.0 | 1.46 | +0.27 | +1.41 | 2.01 |
| trend_rr1 | valid | 9 | 66.7 | 1.51 | +0.20 | +1.37 | 1.62 |
| rsi2_dip | train | 25 | 64.0 | 0.52 | -0.18 | -4.60 | 4.66 |
| rsi2_dip | valid | 17 | **88.2** | 2.26 | +0.16 | +2.76 | 1.07 |
| rsi2_connors | train | 28 | 60.7 | 0.65 | -0.09 | -2.44 | 2.70 |
| rsi2_connors | valid | 18 | 61.1 | 1.50 | +0.05 | +0.84 | 1.04 |
| rsi2_tight | train | 26 | 53.8 | 0.68 | -0.16 | -3.84 | 5.33 |
| rsi2_tight | valid | 16 | 62.5 | 1.00 | +0.00 | +0.02 | 2.42 |
| ema_pullback | train | 21 | 38.1 | 0.48 | -0.37 | -5.69 | 5.69 |
| ema_pullback | valid | 16 | 56.2 | 0.81 | -0.00 | -1.25 | 3.23 |
| bb_reversion | train | 11 | 45.5 | 0.52 | -0.29 | -2.92 | 3.20 |
| bb_reversion | valid | 5 | 60.0 | 0.91 | -0.03 | -0.19 | 2.15 |

## Honest conclusions

1. **No strategy wins everywhere.** Every variant flips between profit and loss
   across periods. Anyone who claims otherwise is overfitting (or lying).
2. **Total expectancy over ALL data (train+valid, both datasets), in R:**
   trend_rider **+7.4R** > trend_rr1 +2.1R > everything else negative.
   The current default remains the best overall performer.
3. **rsi2_dip delivers the highest win rate (83-88% on validation)** and the
   highest validation PF, but it LOST money on both training periods — its
   edge appears only in some market regimes. High win rate ≠ more profit:
   it wins often, small, and occasionally gives a lot back.
4. ema_pullback and bb_reversion underperformed everywhere — kept in the code
   for reference, not recommended.
5. All samples are small (5-79 trades). Treat every number as an estimate,
   not a promise.

**Bot default stays `trend_rider`.** If you want the high-win-rate style,
set `STRATEGY=rsi2_dip` in `.env` — but understand point 3 above.

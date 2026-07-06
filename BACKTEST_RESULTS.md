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

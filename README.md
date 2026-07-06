# Multi-Asset Trend Rider Bot (Crypto + Forex)

Automated trading bot that scans **crypto (CoinDCX)** and **forex (Yahoo Finance data)**,
finds high-probability trend trades, and sets **SL / TP automatically** based on
market volatility (ATR).

## ⚠️ Read this first

- **No strategy in the world guarantees profit.** Anyone selling a "best strategy
  that always wins" is scamming you. This bot uses a professionally respected,
  rules-based trend-following system with strict risk management — that is the
  realistic "best" you can do.
- **Start in paper mode** (`USE_REAL_ORDERS=false`, the default). Run it for at
  least 2–4 weeks and study `trades.csv` before risking real money.
- **Never commit API keys to GitHub.** Keys live only in your local `.env` file.
  If you ever pushed keys to GitHub (even once), **delete/rotate them immediately**
  on CoinDCX and revoke your Telegram bot token via @BotFather.
- Forex trades are **signals + paper only** — the bot tells you on Telegram and
  you execute at your own broker. Crypto can optionally place real CoinDCX orders.

## Strategy: Triple-Confirmation Trend Rider

A trade is taken only when **all three** confirmations agree:

| # | Check | Rule |
|---|-------|------|
| 1 | Trend | Price above EMA200 on 1h chart (long) / below (short, forex only) |
| 2 | Trigger | Fresh EMA9/EMA21 crossover on 5m chart in trend direction |
| 3 | Momentum | RSI(14) in healthy zone + MACD histogram confirming |

**SL / TP set automatically per trade from ATR (volatility):**

- Stop loss = 1.5 × ATR — wide enough to survive noise, tight enough to protect
- Take profit = 3 × ATR — fixed **1:2 risk-reward** (win 40% of trades and still profit)
- Breakeven: after +1 × ATR profit, SL moves to entry (trade becomes risk-free)
- Trailing: chandelier stop 2 × ATR behind the peak locks in profits on big runs

**Risk management (the real "secret" of profitable trading):**

- Only **1% of balance risked per trade**
- Max 3 open trades, max 15 trades/day
- Daily loss cap 3% — bot pauses automatically
- 30-minute cooldown per symbol after an exit

## Choosing a strategy

Seven strategies are built in — set `STRATEGY` in `.env`:

| Strategy | Style | Backtest character |
|---|---|---|
| `trend_rider` (default) | trend-following, RR 1:2 + trailing | best overall expectancy, WR ~35-40% |
| `trend_rr1` | same entries, RR 1:1 | higher WR (~50-70%), smaller edge |
| `rsi2_dip` | Connors RSI(2) mean reversion | highest WR (65-88%) but regime-dependent |
| `rsi2_connors` / `rsi2_tight` | RSI(2) variants | middle ground |
| `ema_pullback` / `bb_reversion` | dip-buying | underperformed in tests |

Compare them yourself on real data: `pip install backtesting && python strategy_lab.py`.
Full numbers in [BACKTEST_RESULTS.md](BACKTEST_RESULTS.md).

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env     # then edit .env with your values
python bot.py
```

For Telegram alerts: create a bot with @BotFather, put the token and your chat id
in `.env`.

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Main loop: scanning, entries/exits, Telegram, journal |
| `strategy.py` | Signal engines (7 selectable strategies) + automatic SL/TP/trailing |
| `strategy_lab.py` | Compare all strategies on real data with train/validation split |
| `indicators.py` | EMA, RSI, MACD, ATR (pure Python) |
| `datafeed.py` | CoinDCX + Yahoo Finance candle feeds |
| `config.py` | All settings, loaded from `.env` |
| `trades.csv` | Auto-generated trade journal — review it weekly |

## Disclaimer

For educational purposes. Trading crypto and forex involves substantial risk of
loss. You are solely responsible for any trades executed with this software.

# ==========================================
# Multi-Asset Trend Rider Bot (Crypto + Forex)
#
#   - Crypto : CoinDCX (paper by default, real orders optional)
#   - Forex  : signals + paper trading (execute at your own broker)
#
# Strategy: Triple-Confirmation Trend Rider (see strategy.py)
# SL / TP  : set automatically per-trade from ATR volatility
#
# DISCLAIMER: Trading is risky. No strategy guarantees profit.
# Always start in paper mode (USE_REAL_ORDERS=false) and test.
# ==========================================

import csv
import hashlib
import hmac
import json
import os
import time
from datetime import datetime

import requests

import config
import strategy
from datafeed import get_candles

# ==========================
# STATE
# ==========================
balance = config.START_BALANCE
daily_pnl = 0.0
open_trades = {}   # symbol -> trade dict
cooldowns = {}     # symbol -> datetime of last exit
trades_today = 0
last_day = datetime.now().day

SYMBOLS = [(s, "crypto") for s in config.CRYPTO_WATCHLIST] + \
          [(s, "forex") for s in config.FOREX_WATCHLIST]


# ==========================
# TELEGRAM
# ==========================
def send_telegram(msg):
    print(msg, flush=True)
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": config.TELEGRAM_CHAT_ID, "text": msg},
            timeout=10,
        )
    except requests.RequestException:
        pass


# ==========================
# TRADE JOURNAL (CSV)
# ==========================
def journal(row):
    new = not os.path.exists(config.JOURNAL_FILE)
    with open(config.JOURNAL_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow([
                "time", "symbol", "market", "side", "event", "price",
                "qty", "sl", "tp", "pnl", "balance", "reason",
            ])
        w.writerow(row)


# ==========================
# REAL ORDERS (CoinDCX crypto only, optional)
# ==========================
def coindcx_market_order(symbol, side, quantity):
    body = {
        "side": side,  # "buy" / "sell"
        "order_type": "market_order",
        "market": symbol,
        "total_quantity": quantity,
        "timestamp": int(time.time() * 1000),
    }
    payload = json.dumps(body, separators=(",", ":"))
    signature = hmac.new(
        config.COINDCX_API_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    r = requests.post(
        "https://api.coindcx.com/exchange/v1/orders/create",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-AUTH-APIKEY": config.COINDCX_API_KEY,
            "X-AUTH-SIGNATURE": signature,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def place_order(symbol, market, side, quantity):
    """Route order: real only for crypto when enabled; otherwise paper."""
    if config.USE_REAL_ORDERS and market == "crypto":
        try:
            coindcx_market_order(symbol, side, quantity)
            return "REAL"
        except Exception as e:  # fall back to paper, tell the user
            send_telegram(f"⚠️ Real order failed for {symbol}: {str(e)[:120]}\nLogged as paper trade.")
    return "PAPER"


# ==========================
# RISK / SIZING
# ==========================
def position_qty(entry, sl):
    """Risk RISK_PER_TRADE of balance between entry and stop."""
    risk_amount = balance * config.RISK_PER_TRADE
    per_unit_risk = abs(entry - sl)
    if per_unit_risk <= 0:
        return 0
    qty = risk_amount / per_unit_risk
    # never allocate more notional than 25% of balance
    max_qty = (balance * 0.25) / entry
    return round(min(qty, max_qty), 6)


def can_trade(symbol):
    if symbol in open_trades:
        return False
    if trades_today >= config.MAX_TRADES_PER_DAY:
        return False
    if len(open_trades) >= config.MAX_OPEN_TRADES:
        return False
    if symbol in cooldowns:
        mins = (datetime.now() - cooldowns[symbol]).total_seconds() / 60
        if mins < config.COOLDOWN_MIN:
            return False
    return True


# ==========================
# ENTRY / EXIT
# ==========================
def enter_trade(symbol, market, signal):
    global trades_today

    entry = signal["price"]
    sl, tp = strategy.make_levels(signal["side"], entry, signal["atr"])
    qty = position_qty(entry, sl)
    if qty <= 0:
        return

    mode = place_order(symbol, market, "buy" if signal["side"] == "long" else "sell", qty)

    open_trades[symbol] = {
        "market": market,
        "side": signal["side"],
        "entry": entry,
        "qty": qty,
        "sl": sl,
        "tp": tp,
        "atr": signal["atr"],
        "peak": entry,
        "breakeven": False,
        "mode": mode,
        "time": datetime.now(),
    }
    trades_today += 1

    arrow = "🟢 LONG" if signal["side"] == "long" else "🔻 SHORT"
    send_telegram(
        f"{arrow} {symbol} ({market}, {mode})\n"
        f"Entry: {entry:.6g}\n"
        f"SL: {sl:.6g}  (auto, 1.5xATR)\n"
        f"TP: {tp:.6g}  (auto, 3xATR, RR 1:2)\n"
        f"Qty: {qty}\n"
        f"Why: {signal['reason']}"
    )
    journal([
        datetime.now().isoformat(), symbol, market, signal["side"], "ENTRY",
        entry, qty, round(sl, 6), round(tp, 6), "", round(balance, 2), signal["reason"],
    ])


def exit_trade(symbol, reason, price):
    global balance, daily_pnl

    t = open_trades.pop(symbol)
    direction = 1 if t["side"] == "long" else -1
    pnl = (price - t["entry"]) * direction * t["qty"]
    balance += pnl
    daily_pnl += pnl
    cooldowns[symbol] = datetime.now()

    if t["mode"] == "REAL":
        try:
            coindcx_market_order(symbol, "sell" if t["side"] == "long" else "buy", t["qty"])
        except Exception as e:
            send_telegram(f"⚠️ Real exit order failed for {symbol}: {str(e)[:120]} — CLOSE MANUALLY!")

    icon = "✅" if pnl >= 0 else "🔴"
    send_telegram(
        f"{icon} {reason} — {symbol}\n"
        f"Exit: {price:.6g}  (entry {t['entry']:.6g})\n"
        f"PnL: {pnl:+.2f}\n"
        f"Balance: {balance:.2f}  |  Today: {daily_pnl:+.2f}"
    )
    journal([
        datetime.now().isoformat(), symbol, t["market"], t["side"], reason,
        price, t["qty"], round(t["sl"], 6), round(t["tp"], 6),
        round(pnl, 2), round(balance, 2), "",
    ])


def manage_trades():
    for symbol in list(open_trades.keys()):
        t = open_trades[symbol]
        try:
            candles = get_candles(symbol, t["market"], config.TIMEFRAME, 5)
        except Exception:
            continue
        if not candles:
            continue
        price = candles[-1]["close"]

        strategy.update_stop(t, price)
        reason = strategy.check_exit(t, price)
        if reason:
            exit_trade(symbol, reason, price)


# ==========================
# SCANNING
# ==========================
def scan_for_entries():
    for symbol, market in SYMBOLS:
        if not can_trade(symbol):
            continue
        try:
            candles = get_candles(symbol, market, config.TIMEFRAME, config.CANDLE_LIMIT)
            trend = get_candles(symbol, market, config.TREND_TIMEFRAME, config.CANDLE_LIMIT)
        except Exception:
            continue
        signal = strategy.analyze(candles, trend, allow_short=(market == "forex"))
        if signal:
            enter_trade(symbol, market, signal)
        time.sleep(0.5)  # be gentle with the APIs


def reset_if_new_day():
    global last_day, trades_today, daily_pnl
    now = datetime.now()
    if now.day != last_day:
        last_day = now.day
        trades_today = 0
        daily_pnl = 0.0
        send_telegram(f"📅 New day. Balance: {balance:.2f}")


# ==========================
# MAIN LOOP
# ==========================
def run():
    mode = "REAL ORDERS (crypto)" if config.USE_REAL_ORDERS else "PAPER / SIGNALS"
    send_telegram(
        "🚀 Trend Rider Bot started\n"
        f"Mode: {mode}\n"
        f"Crypto: {', '.join(config.CRYPTO_WATCHLIST)}\n"
        f"Forex: {', '.join(config.FOREX_WATCHLIST)}\n"
        f"Risk: {config.RISK_PER_TRADE*100:.1f}%/trade | RR 1:2 | ATR SL/TP"
    )

    while True:
        try:
            reset_if_new_day()

            if daily_pnl <= -abs(config.START_BALANCE * config.DAILY_MAX_LOSS_PCT):
                send_telegram("🛑 Daily max loss hit. Pausing for 1 hour.")
                time.sleep(3600)
                continue

            manage_trades()
            scan_for_entries()
            time.sleep(config.SCAN_DELAY)

        except KeyboardInterrupt:
            send_telegram("👋 Bot stopped by user.")
            break
        except Exception as e:
            send_telegram(f"⚠️ Error: {str(e)[:150]}")
            time.sleep(30)


if __name__ == "__main__":
    run()

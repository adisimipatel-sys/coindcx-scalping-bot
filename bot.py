# ==========================================
# CoinDCX Smart Bot V3 (Signal + Paper Trade)
# Single File Version
# ==========================================

import time
import math
import requests
from datetime import datetime

# ==========================
# USER SETTINGS
# ==========================
API_KEY = "d75f901dc7edac19d582195810cb222719a1481be8cbe533"
API_SECRET = "f61a969b5afac77a0f4dba48a3822ed0e54e4d30b64be0a2ffbe91f4cd2dff82"

BOT_TOKEN = "8590310543:AAEWkM5pqmNvVuN1Y_9b7d9zfu-tIlnVnA8"
CHAT_ID = "5459407256"

USE_REAL_ORDERS = False      # False = signals/paper mode
RISK_PER_TRADE = 0.25        # 25% balance sizing
START_BALANCE = 2000
MAX_OPEN_TRADES = 2
SCAN_DELAY = 20             # seconds
COOLDOWN_MIN = 20           # after exit same coin cooldown
DAILY_MAX_LOSS = -150
MAX_TRADES_PER_DAY = 25

WATCHLIST = [
    "BTCINR","ETHINR","SOLINR","XRPINR","BNBINR",
    "DOGEINR","ADAINR","LINKINR"
]

# ==========================
# GLOBALS
# ==========================
balance = START_BALANCE
daily_pnl = 0
open_trades = {}
cooldowns = {}
trades_today = 0
last_day = datetime.now().day

# ==========================
# TELEGRAM
# ==========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except:
        pass

# ==========================
# MARKET DATA
# ==========================
def get_all_tickers():
    try:
        return requests.get("https://api.coindcx.com/exchange/ticker", timeout=10).json()
    except:
        return []

def get_price(symbol):
    data = get_all_tickers()
    for x in data:
        if x.get("market") == symbol:
            try:
                return float(x["last_price"])
            except:
                return 0
    return 0

# ==========================
# SIMPLE SIGNAL ENGINE
# ==========================
def score_signal(symbol, price):
    # lightweight pseudo scoring from price structure
    frac = price - int(price)
    score = 0

    if frac > 0.15:
        score += 1
    if int(price) % 2 == 0:
        score += 1
    if int(price) % 5 in [1,2]:
        score += 1
    if price > 0:
        score += 1

    return score

def should_buy(symbol):
    price = get_price(symbol)
    if price <= 0:
        return False, 0

    score = score_signal(symbol, price)

    # Need decent score
    if score >= 3:
        return True, price

    return False, price

# ==========================
# TRADE LOGIC
# ==========================
def position_size():
    global balance
    amt = max(300, balance * RISK_PER_TRADE)
    return round(min(amt, balance), 2)

def adaptive_levels(price):
    # adaptive TP / SL
    tp = price * 1.0075   # +0.75%
    sl = price * 0.9955   # -0.45%
    trail = price * 1.004
    return tp, sl, trail

def can_trade(symbol):
    global trades_today

    if symbol in open_trades:
        return False

    if trades_today >= MAX_TRADES_PER_DAY:
        return False

    if symbol in cooldowns:
        mins = (datetime.now() - cooldowns[symbol]).total_seconds() / 60
        if mins < COOLDOWN_MIN:
            return False

    if len(open_trades) >= MAX_OPEN_TRADES:
        return False

    return True

def enter_trade(symbol, price):
    global open_trades, trades_today

    amt = position_size()
    tp, sl, trail = adaptive_levels(price)

    open_trades[symbol] = {
        "entry": price,
        "amount": amt,
        "tp": tp,
        "sl": sl,
        "trail": trail,
        "peak": price,
        "time": datetime.now()
    }

    trades_today += 1

    send_telegram(
        f"🟢 BUY SIGNAL\n"
        f"{symbol}\n"
        f"Entry: {price}\n"
        f"Amount: ₹{amt}\n"
        f"TP: {round(tp,4)}\n"
        f"SL: {round(sl,4)}"
    )

def exit_trade(symbol, reason, price):
    global open_trades, balance, daily_pnl, cooldowns

    t = open_trades[symbol]
    entry = t["entry"]
    amt = t["amount"]

    pnl_pct = (price - entry) / entry
    pnl = amt * pnl_pct

    balance += pnl
    daily_pnl += pnl
    cooldowns[symbol] = datetime.now()

    icon = "✅" if pnl >= 0 else "🔴"

    send_telegram(
        f"{icon} {reason}\n"
        f"{symbol}\n"
        f"Exit: {price}\n"
        f"PnL: ₹{round(pnl,2)}\n"
        f"Balance: ₹{round(balance,2)}"
    )

    del open_trades[symbol]

def manage_trades():
    for symbol in list(open_trades.keys()):
        t = open_trades[symbol]
        live = get_price(symbol)
        if live <= 0:
            continue

        # peak update
        if live > t["peak"]:
            t["peak"] = live

        # hybrid logic: partial/trailing style
        if live >= t["tp"]:
            exit_trade(symbol, "TARGET HIT", live)
            continue

        # trailing if moved enough then falls
        if t["peak"] >= t["trail"] and live < t["peak"] * 0.998:
            exit_trade(symbol, "TRAIL EXIT", live)
            continue

        if live <= t["sl"]:
            exit_trade(symbol, "STOP LOSS", live)
            continue

# ==========================
# DAILY RESET
# ==========================
def reset_if_new_day():
    global last_day, trades_today, daily_pnl
    now = datetime.now()
    if now.day != last_day:
        last_day = now.day
        trades_today = 0
        daily_pnl = 0

# ==========================
# MAIN LOOP
# ==========================
def run():
    send_telegram("🚀 CoinDCX Smart Bot V3 Started")

    while True:
        try:
            reset_if_new_day()

            if daily_pnl <= DAILY_MAX_LOSS:
                send_telegram("🛑 Daily max loss hit. Sleeping 1 hour.")
                time.sleep(3600)
                continue

            manage_trades()

            for symbol in WATCHLIST:
                if can_trade(symbol):
                    ok, price = should_buy(symbol)
                    if ok:
                        enter_trade(symbol, price)

            time.sleep(SCAN_DELAY)

        except Exception as e:
            send_telegram(f"⚠️ Error: {str(e)[:120]}")
            time.sleep(15)

# ==========================
# START
# ==========================
if __name__ == "__main__":
    run()
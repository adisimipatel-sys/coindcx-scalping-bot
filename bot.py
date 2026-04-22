# ==========================================
# CoinDCX Auto Trade Bot V2 Final
# Pydroid 3 / GitHub Ready
# Crypto Scalping Demo Structure
# ==========================================

import time
import requests
from datetime import datetime

# ==========================
# USER SETTINGS
# ==========================
API_KEY = "d75f901dc7edac19d582195810cb222719a1481be8cbe533"
API_SECRET = "f61a969b5afac77a0f4dba48a3822ed0e54e4d30b64be0a2ffbe91f4cd2dff82"

BOT_TOKEN = "8590310543:AAEWkM5pqmNvVuN1Y_9b7d9zfu-tIlnVnA8"
CHAT_ID = "5459407256"

TRADE_AMOUNT = 500        # per trade INR
TAKE_PROFIT = 0.012       # 1.2%
STOP_LOSS = 0.006         # 0.6%
MAX_OPEN_TRADES = 2
DAILY_MAX_LOSS = -150
SCAN_DELAY = 10

WATCHLIST = [
    "BTCINR",
    "ETHINR",
    "SOLINR",
    "XRPINR",
    "DOGEINR"
]

# ==========================
# GLOBALS
# ==========================
open_trades = {}
daily_pnl = 0

# ==========================
# TELEGRAM ALERT
# ==========================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": CHAT_ID,
            "text": msg
        }
        requests.post(url, data=data, timeout=10)
    except:
        pass

# ==========================
# GET LIVE PRICE
# ==========================
def get_price(symbol):
    try:
        url = "https://api.coindcx.com/exchange/ticker"
        data = requests.get(url, timeout=10).json()

        for coin in data:
            if coin["market"] == symbol:
                return float(coin["last_price"])

    except:
        return 0

    return 0

# ==========================
# ENTRY SIGNAL
# ==========================
def should_buy(symbol):
    # simple momentum logic demo
    price = get_price(symbol)

    if price == 0:
        return False

    last2 = int(price) % 7

    if last2 in [1, 3, 5]:
        return True

    return False

# ==========================
# BUY TRADE
# ==========================
def buy_trade(symbol):
    global open_trades

    price = get_price(symbol)

    if price == 0:
        return

    open_trades[symbol] = {
        "entry": price,
        "time": datetime.now()
    }

    send_telegram(
        f"🟢 BUY SIGNAL\n"
        f"Coin: {symbol}\n"
        f"Entry: {price}\n"
        f"Amount: ₹{TRADE_AMOUNT}"
    )

# ==========================
# MANAGE TRADE
# ==========================
def manage_trade(symbol):
    global daily_pnl
    global open_trades

    trade = open_trades[symbol]

    entry = trade["entry"]
    live = get_price(symbol)

    if live == 0:
        return

    change = (live - entry) / entry

    # TAKE PROFIT
    if change >= TAKE_PROFIT:
        profit = TRADE_AMOUNT * TAKE_PROFIT
        daily_pnl += profit

        send_telegram(
            f"✅ TARGET HIT\n"
            f"{symbol}\n"
            f"Exit: {live}\n"
            f"Profit: ₹{round(profit,2)}"
        )

        del open_trades[symbol]

    # STOP LOSS
    elif change <= -STOP_LOSS:
        loss = TRADE_AMOUNT * STOP_LOSS
        daily_pnl -= loss

        send_telegram(
            f"🔴 STOP LOSS HIT\n"
            f"{symbol}\n"
            f"Exit: {live}\n"
            f"Loss: ₹{round(loss,2)}"
        )

        del open_trades[symbol]

# ==========================
# MAIN LOOP
# ==========================
def run_bot():
    global daily_pnl

    send_telegram("🚀 CoinDCX Bot V2 Started")

    while True:

        # max loss stop
        if daily_pnl <= DAILY_MAX_LOSS:
            send_telegram("🛑 Daily Max Loss Hit. Bot Sleeping.")
            time.sleep(3600)
            continue

        # manage old trades
        for coin in list(open_trades.keys()):
            manage_trade(coin)

        # new trades
        if len(open_trades) < MAX_OPEN_TRADES:

            for coin in WATCHLIST:

                if coin not in open_trades:

                    if should_buy(coin):
                        buy_trade(coin)

                        if len(open_trades) >= MAX_OPEN_TRADES:
                            break

        time.sleep(SCAN_DELAY)

# ==========================
# START
# ==========================
if __name__ == "__main__":
    run_bot()
#!/usr/bin/env python3
"""
HFT Scalping Bot v3.0 - CoinDCX (India)
7-Indicator Confluence System
Target: 60%+ win rate, auto-trade on CoinDCX
"""

import hashlib
import hmac
import json
import os
import time
import math
import logging
from datetime import datetime
from typing import Optional
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
COINDCX_API_KEY     = os.getenv("COINDCX_API_KEY", "")
COINDCX_SECRET_KEY  = os.getenv("COINDCX_SECRET_KEY", "")

# CoinDCX symbols (market format: BTCINR, ETHINR etc)
SYMBOLS = [
    {"dcx": "BTCINR",  "cg": "bitcoin"},
    {"dcx": "ETHINR",  "cg": "ethereum"},
    {"dcx": "BNBINR",  "cg": "binancecoin"},
    {"dcx": "SOLINR",  "cg": "solana"},
    {"dcx": "XRPINR",  "cg": "ripple"},
]

TRADE_AMOUNT_INR   = 200      # ₹200 per trade
PROFIT_TARGET_PCT  = 0.004    # 0.4%
STOP_LOSS_PCT      = 0.002    # 0.2%
SCAN_INTERVAL_SEC  = 60
MIN_CONFLUENCE     = 4        # 4/7 indicators must agree
COINDCX_BASE_URL   = "https://api.coindcx.com"

# Stats
stats = {
    "total_trades": 0,
    "wins": 0,
    "losses": 0,
    "total_pnl": 0.0,
}
active_trades = {}

# ─── COINDCX API ──────────────────────────────────────────────────────────────

def dcx_sign(body: dict) -> tuple:
    json_body = json.dumps(body, separators=(',', ':'))
    secret_bytes = bytes(COINDCX_SECRET_KEY, encoding='utf-8')
    signature = hmac.new(secret_bytes, json_body.encode(), hashlib.sha256).hexdigest()
    return json_body, signature

def dcx_request(endpoint: str, body: dict) -> dict:
    json_body, signature = dcx_sign(body)
    headers = {
        'Content-Type': 'application/json',
        'X-AUTH-APIKEY': COINDCX_API_KEY,
        'X-AUTH-SIGNATURE': signature
    }
    try:
        r = requests.post(
            f"{COINDCX_BASE_URL}{endpoint}",
            data=json_body,
            headers=headers,
            timeout=15
        )
        return r.json()
    except Exception as e:
        logger.error(f"CoinDCX API error: {e}")
        return {}

def get_candles_coindcx(symbol_dcx: str) -> list:
    """Get candles from CoinDCX public API"""
    try:
        # CoinDCX public candles endpoint
        r = requests.get(
            f"{COINDCX_BASE_URL}/market_data/candles",
            params={
                "pair": symbol_dcx,
                "interval": "1m",
                "limit": 150
            },
            timeout=15
        )
        data = r.json()
        if not isinstance(data, list) or len(data) == 0:
            return []
        candles = []
        for c in data:
            candles.append({
                "time":   float(c.get("time", 0)),
                "open":   float(c.get("open", 0)),
                "high":   float(c.get("high", 0)),
                "low":    float(c.get("low", 0)),
                "close":  float(c.get("close", 0)),
                "volume": float(c.get("volume", 0)),
            })
        return candles
    except Exception as e:
        logger.error(f"CoinDCX candles error {symbol_dcx}: {e}")
        return []


def get_ticker_coindcx(symbol_dcx: str) -> Optional[float]:
    """Get current price from CoinDCX ticker"""
    try:
        r = requests.get(f"{COINDCX_BASE_URL}/exchange/ticker", timeout=10)
        tickers = r.json()
        for t in tickers:
            if t.get("market") == symbol_dcx:
                return float(t.get("last_price", 0))
        return None
    except Exception as e:
        logger.error(f"Ticker error: {e}")
        return None


def get_orderbook_coindcx(symbol_dcx: str) -> dict:
    """Get order book from CoinDCX"""
    try:
        r = requests.get(
            f"{COINDCX_BASE_URL}/market_data/orderbook",
            params={"pair": symbol_dcx},
            timeout=10
        )
        data = r.json()
        bids = sum(float(b[1]) for b in data.get("bids", [])[:10])
        asks = sum(float(a[1]) for a in data.get("asks", [])[:10])
        return {"bids": bids, "asks": asks}
    except:
        return {"bids": 500, "asks": 500}


def place_order_coindcx(symbol_dcx: str, side: str, amount_inr: float, price: float) -> dict:
    """Place market order on CoinDCX"""
    try:
        # Calculate quantity
        quantity = round(amount_inr / price, 6)
        timestamp = int(round(time.time() * 1000))

        body = {
            "side": side.lower(),  # "buy" or "sell"
            "order_type": "market_order",
            "market": symbol_dcx,
            "total_quantity": quantity,
            "timestamp": timestamp
        }

        result = dcx_request("/exchange/v1/orders/create", body)
        logger.info(f"  Order result: {result}")
        return result
    except Exception as e:
        logger.error(f"Order error: {e}")
        return {}

# ─── INDICATORS ───────────────────────────────────────────────────────────────

def calc_rsi(closes: list, period=14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


def calc_ema(closes: list, period: int) -> list:
    if len(closes) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]
    for price in closes[period:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def calc_vwap(candles: list) -> float:
    try:
        total_pv  = sum(((c["high"] + c["low"] + c["close"]) / 3) * c["volume"] for c in candles)
        total_vol = sum(c["volume"] for c in candles)
        return round(total_pv / total_vol, 2) if total_vol > 0 else 0
    except:
        return 0


def calc_bollinger(closes: list, period=20) -> dict:
    if len(closes) < period:
        return {"upper": 0, "middle": 0, "lower": 0, "width": 0, "squeeze": False}
    recent = closes[-period:]
    middle = sum(recent) / period
    std    = math.sqrt(sum((x - middle) ** 2 for x in recent) / period)
    upper  = middle + 2 * std
    lower  = middle - 2 * std
    width  = (upper - lower) / middle * 100
    return {
        "upper":   round(upper, 2),
        "middle":  round(middle, 2),
        "lower":   round(lower, 2),
        "width":   round(width, 4),
        "squeeze": width < 1.0
    }


def calc_support_resistance(candles: list, lookback=50) -> dict:
    if len(candles) < lookback:
        return {"support": [], "resistance": []}
    recent = candles[-lookback:]
    highs  = [c["high"]  for c in recent]
    lows   = [c["low"]   for c in recent]
    price  = candles[-1]["close"]

    res_levels = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
           highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            res_levels.append(highs[i])

    sup_levels = []
    for i in range(2, len(lows) - 2):
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
           lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            sup_levels.append(lows[i])

    def cluster(levels, threshold=0.003):
        if not levels:
            return []
        levels = sorted(levels)
        clustered = [levels[0]]
        for level in levels[1:]:
            if abs(level - clustered[-1]) / clustered[-1] > threshold:
                clustered.append(level)
            else:
                clustered[-1] = (clustered[-1] + level) / 2
        return clustered

    support    = sorted([s for s in cluster(sup_levels) if s < price], reverse=True)[:3]
    resistance = sorted([r for r in cluster(res_levels) if r > price])[:3]
    return {"support": support, "resistance": resistance}


def calc_volume_analysis(candles: list) -> dict:
    volumes = [c["volume"] for c in candles]
    if len(volumes) < 20:
        return {"ratio": 1.0, "signal": "NORMAL"}
    avg_vol  = sum(volumes[-20:-1]) / 19
    last_vol = volumes[-1]
    ratio    = last_vol / avg_vol if avg_vol > 0 else 1.0
    signal   = "HIGH" if ratio >= 1.5 else "NORMAL"
    return {"ratio": round(ratio, 2), "signal": signal}


def calc_macd(closes: list) -> dict:
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    if not ema12 or not ema26:
        return {"histogram": 0, "signal_cross": "NEUTRAL"}
    min_len   = min(len(ema12), len(ema26))
    macd_line = [ema12[-(min_len-i)] - ema26[-(min_len-i)] for i in range(min_len)]
    sig_ema   = calc_ema(macd_line, 9)
    if not sig_ema:
        return {"histogram": 0, "signal_cross": "NEUTRAL"}
    hist_now  = macd_line[-1] - sig_ema[-1]
    hist_prev = macd_line[-2] - sig_ema[-2] if len(macd_line) >= 2 else 0
    if hist_prev < 0 and hist_now > 0:
        cross = "BULLISH_CROSS"
    elif hist_prev > 0 and hist_now < 0:
        cross = "BEARISH_CROSS"
    elif hist_now > 0:
        cross = "BULLISH"
    else:
        cross = "BEARISH"
    return {"histogram": round(hist_now, 2), "signal_cross": cross}

# ─── SIGNAL ENGINE ────────────────────────────────────────────────────────────

def generate_signal(symbol: dict, candles: list) -> Optional[dict]:
    if len(candles) < 100:
        return None

    closes = [c["close"] for c in candles]
    price  = closes[-1]
    prev   = closes[-2]

    rsi  = calc_rsi(closes)
    bb   = calc_bollinger(closes)
    sr   = calc_support_resistance(candles)
    vol  = calc_volume_analysis(candles)
    vwap = calc_vwap(candles[-50:])
    macd = calc_macd(closes)
    ema9 = calc_ema(closes, 9)
    ema21= calc_ema(closes, 21)
    ob   = get_orderbook_coindcx(symbol["dcx"])

    buy_signals  = []
    sell_signals = []

    # 1. RSI
    if rsi < 35:
        buy_signals.append(f"RSI={rsi} Oversold 🟢")
    elif rsi > 65:
        sell_signals.append(f"RSI={rsi} Overbought 🔴")
    elif rsi <= 50:
        buy_signals.append(f"RSI={rsi} Bullish zone")
    else:
        sell_signals.append(f"RSI={rsi} Bearish zone")

    # 2. EMA
    if ema9 and ema21:
        if ema9[-1] > ema21[-1] and price > ema9[-1]:
            buy_signals.append("EMA9>EMA21 Uptrend 🟢")
        elif ema9[-1] < ema21[-1] and price < ema9[-1]:
            sell_signals.append("EMA9<EMA21 Downtrend 🔴")

    # 3. VWAP
    if vwap > 0:
        if price > vwap * 1.001:
            buy_signals.append(f"Above VWAP {vwap:.0f} 🟢")
        elif price < vwap * 0.999:
            sell_signals.append(f"Below VWAP {vwap:.0f} 🔴")

    # 4. Bollinger
    if bb["squeeze"]:
        if price > prev:
            buy_signals.append(f"BB Squeeze Breakout UP 🟢")
        else:
            sell_signals.append(f"BB Squeeze Breakout DOWN 🔴")
    else:
        if price <= bb["lower"] * 1.001:
            buy_signals.append("Price at BB Lower 🟢")
        elif price >= bb["upper"] * 0.999:
            sell_signals.append("Price at BB Upper 🔴")

    # 5. Support/Resistance
    def near(p, level, pct=0.003):
        return abs(p - level) / level <= pct

    for sup in sr["support"]:
        if near(price, sup) and price >= prev:
            buy_signals.append(f"Bounce from Support {sup:.0f} 🟢")
            break
        if prev > sup >= price:
            sell_signals.append(f"Break below Support {sup:.0f} 🔴")
            break

    for res in sr["resistance"]:
        if near(price, res) and price <= prev:
            sell_signals.append(f"Rejection at Resistance {res:.0f} 🔴")
            break
        if prev < res <= price:
            buy_signals.append(f"Breakout above Resistance {res:.0f} 🟢")
            break

    # 6. Volume
    if vol["signal"] == "HIGH":
        if price > prev:
            buy_signals.append(f"High Volume {vol['ratio']}x 🟢")
        else:
            sell_signals.append(f"High Volume {vol['ratio']}x 🔴")

    # 7. Order Flow + MACD
    total_ob = ob["bids"] + ob["asks"]
    if total_ob > 0:
        buy_pct = ob["bids"] / total_ob * 100
        if buy_pct >= 60:
            buy_signals.append(f"Order Flow Bullish {buy_pct:.0f}% 🟢")
        elif buy_pct <= 40:
            sell_signals.append(f"Order Flow Bearish {100-buy_pct:.0f}% sell 🔴")

    if macd["signal_cross"] in ("BULLISH_CROSS", "BULLISH"):
        buy_signals.append(f"MACD {macd['signal_cross']} 🟢")
    elif macd["signal_cross"] in ("BEARISH_CROSS", "BEARISH"):
        sell_signals.append(f"MACD {macd['signal_cross']} 🔴")

    # Confluence check
    buy_count  = len(buy_signals)
    sell_count = len(sell_signals)

    if buy_count >= MIN_CONFLUENCE and buy_count >= sell_count:
        direction  = "BUY"
        reasons    = buy_signals
        confluence = buy_count
    elif sell_count >= MIN_CONFLUENCE and sell_count > buy_count:
        direction  = "SELL"
        reasons    = sell_signals
        confluence = sell_count
    else:
        return None

    confidence = min(50 + confluence * 8, 95)
    if vol["signal"] == "HIGH":
        confidence = min(confidence + 5, 95)
    if bb["squeeze"]:
        confidence = min(confidence + 5, 95)

    if direction == "BUY":
        stop_loss = round(price * (1 - STOP_LOSS_PCT), 2)
        target    = round(price * (1 + PROFIT_TARGET_PCT), 2)
    else:
        stop_loss = round(price * (1 + STOP_LOSS_PCT), 2)
        target    = round(price * (1 - PROFIT_TARGET_PCT), 2)

    return {
        "symbol":      symbol["dcx"],
        "direction":   direction,
        "price":       price,
        "stop_loss":   stop_loss,
        "target":      target,
        "confidence":  confidence,
        "confluence":  f"{confluence}/7",
        "rsi":         rsi,
        "volume_ratio":vol["ratio"],
        "bb_squeeze":  bb["squeeze"],
        "reasons":     reasons,
        "timestamp":   datetime.now().isoformat(),
    }

# ─── TRADE EXECUTION ──────────────────────────────────────────────────────────

def execute_trade(signal: dict) -> Optional[dict]:
    symbol = signal["symbol"]
    price  = signal["price"]
    side   = "buy" if signal["direction"] == "BUY" else "sell"

    logger.info(f"  🔄 Placing {side.upper()} {symbol} @ ~₹{price}")
    order = place_order_coindcx(symbol, side, TRADE_AMOUNT_INR, price)

    if not order or "id" not in order:
        logger.error(f"  ❌ Order failed: {order}")
        return None

    logger.info(f"  ✅ Order placed! ID: {order.get('id')}")

    active_trades[symbol] = {
        "order_id":  order.get("id"),
        "direction": signal["direction"],
        "entry":     price,
        "qty":       TRADE_AMOUNT_INR / price,
        "stop_loss": signal["stop_loss"],
        "target":    signal["target"],
        "open_time": time.time(),
        "confidence":signal["confidence"],
    }
    return order


def check_exit(symbol: str) -> Optional[str]:
    if symbol not in active_trades:
        return None
    trade = active_trades[symbol]
    price = get_ticker_coindcx(symbol)
    if not price:
        return None

    if trade["direction"] == "BUY":
        if price >= trade["target"]:    return "TARGET_HIT"
        if price <= trade["stop_loss"]: return "STOP_LOSS"
    else:
        if price <= trade["target"]:    return "TARGET_HIT"
        if price >= trade["stop_loss"]: return "STOP_LOSS"

    if time.time() - trade["open_time"] > 300:
        return "TIMEOUT"
    return None


def close_trade(symbol: str, exit_reason: str):
    if symbol not in active_trades:
        return
    trade      = active_trades[symbol]
    exit_price = get_ticker_coindcx(symbol) or trade["entry"]
    close_side = "sell" if trade["direction"] == "BUY" else "buy"

    order = place_order_coindcx(symbol, close_side, TRADE_AMOUNT_INR, exit_price)

    if order:
        entry = trade["entry"]
        if trade["direction"] == "BUY":
            pnl_pct = (exit_price - entry) / entry * 100
        else:
            pnl_pct = (entry - exit_price) / entry * 100

        pnl_inr = TRADE_AMOUNT_INR * pnl_pct / 100
        fees    = TRADE_AMOUNT_INR * 0.002
        net_pnl = pnl_inr - fees
        result  = "WIN" if net_pnl > 0 else "LOSS"

        stats["total_trades"] += 1
        stats["wins"]   += 1 if result == "WIN" else 0
        stats["losses"] += 1 if result == "LOSS" else 0
        stats["total_pnl"] += net_pnl

        logger.info(f"  {'✅' if result=='WIN' else '❌'} {symbol} {result}: ₹{net_pnl:+.2f} | {exit_reason}")
        send_result_telegram(symbol, trade, exit_price, net_pnl, pnl_pct, result, exit_reason)
        del active_trades[symbol]

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def tg_send(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
    except:
        pass


def send_signal_telegram(signal: dict, order: dict):
    emoji = "🟢" if signal["direction"] == "BUY" else "🔴"
    reasons = "\n".join(f"• {r}" for r in signal["reasons"][:5])
    tg_send(f"""
⚡ <b>SCALP TRADE OPENED</b>

{emoji} <b>{signal['direction']}</b> {signal['symbol']}
<b>Entry:</b> ₹{signal['price']:,.2f}
<b>Target:</b> ₹{signal['target']:,.2f} (+0.4%)
<b>Stop Loss:</b> ₹{signal['stop_loss']:,.2f} (-0.2%)
<b>Confidence:</b> {signal['confidence']}%
<b>Confluence:</b> {signal['confluence']}

<b>📊 Signals:</b>
{reasons}

<b>Volume:</b> {signal['volume_ratio']}x avg
<b>RSI:</b> {signal['rsi']}
<b>BB Squeeze:</b> {'YES 🔥' if signal['bb_squeeze'] else 'No'}

<i>⏰ {signal['timestamp'][:16]}</i>
""".strip())


def send_result_telegram(symbol, trade, exit_price, net_pnl, pnl_pct, result, reason):
    emoji    = "✅" if result == "WIN" else "❌"
    win_rate = round(stats["wins"] / stats["total_trades"] * 100, 1) if stats["total_trades"] > 0 else 0
    tg_send(f"""
{emoji} <b>TRADE CLOSED — {result}</b>

<b>Symbol:</b> {symbol}
<b>Direction:</b> {trade['direction']}
<b>Entry:</b> ₹{trade['entry']:,.2f} → <b>Exit:</b> ₹{exit_price:,.2f}
<b>P&L:</b> ₹{net_pnl:+.2f} ({pnl_pct:+.3f}%)
<b>Reason:</b> {reason}

<b>📊 Today's Stats:</b>
• Trades: {stats['total_trades']}
• Win Rate: {win_rate}%
• Total P&L: ₹{stats['total_pnl']:+.2f}
<i>⏰ {datetime.now().strftime('%H:%M:%S')}</i>
""".strip())


def send_daily_summary():
    win_rate = round(stats["wins"] / stats["total_trades"] * 100, 1) if stats["total_trades"] > 0 else 0
    tg_send(f"""
📊 <b>DAILY SCALPING SUMMARY</b>

<b>Total Trades:</b> {stats['total_trades']}
<b>Wins:</b> {stats['wins']} ✅
<b>Losses:</b> {stats['losses']} ❌
<b>Win Rate:</b> {win_rate}%
<b>Net P&L:</b> ₹{stats['total_pnl']:+.2f}

<b>🎯 Exchange:</b> CoinDCX (India)
<b>📡 Indicators:</b> RSI+EMA+VWAP+BB+S/R+Volume+OrderFlow
<i>⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}</i>
""".strip())

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    logger.info("🚀 HFT Scalping Bot v3.0 — CoinDCX India!")
    logger.info(f"📊 Symbols: {[s['dcx'] for s in SYMBOLS]}")
    logger.info(f"💰 Per trade: ₹{TRADE_AMOUNT_INR}")
    logger.info(f"🎯 Target: +{PROFIT_TARGET_PCT*100}% | Stop: -{STOP_LOSS_PCT*100}%")
    logger.info(f"🔀 Min confluence: {MIN_CONFLUENCE}/7")
    logger.info(f"🔑 CoinDCX: {'✅' if COINDCX_API_KEY else '❌'}")
    logger.info(f"📱 Telegram: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}")

    if not COINDCX_API_KEY or not COINDCX_SECRET_KEY:
        logger.error("❌ CoinDCX API keys missing!")
        return

    tg_send("🚀 <b>HFT Scalping Bot v3.0 Started!</b>\n\n📊 Exchange: CoinDCX India\n📡 BTC, ETH, BNB, SOL, XRP (INR pairs)\n🎯 Target: +0.4% | Stop: -0.2%\n🔀 7-Indicator Confluence System\n\nBot is live! ⚡")

    last_summary = datetime.now().date()
    scan_count   = 0

    while True:
        try:
            scan_count += 1
            logger.info(f"\n{'='*40}")
            logger.info(f"🔍 Scan #{scan_count} | Active: {len(active_trades)} | Trades: {stats['total_trades']} | P&L: ₹{stats['total_pnl']:+.2f}")

            # Check exits first
            for sym in list(active_trades.keys()):
                exit_reason = check_exit(sym)
                if exit_reason:
                    close_trade(sym, exit_reason)

            # Scan for signals
            for symbol in SYMBOLS:
                dcx = symbol["dcx"]
                if dcx in active_trades:
                    logger.info(f"  ⏭️ {dcx} — trade active")
                    continue

                candles = get_candles_coindcx(dcx)
                if not candles:
                    logger.info(f"  ❌ {dcx}: No data")
                    time.sleep(2)
                    continue

                signal = generate_signal(symbol, candles)

                if signal:
                    logger.info(f"  ⚡ {dcx}: {signal['direction']} | {signal['confidence']}% | {signal['confluence']}")
                    order = execute_trade(signal)
                    if order:
                        send_signal_telegram(signal, order)
                else:
                    logger.info(f"  — {dcx}: No signal")

                time.sleep(2)

            # Daily summary
            today = datetime.now().date()
            if today != last_summary:
                send_daily_summary()
                stats.update({"total_trades": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
                last_summary = today

            time.sleep(SCAN_INTERVAL_SEC)

        except KeyboardInterrupt:
            logger.info("Bot stopped!")
            send_daily_summary()
            break
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            time.sleep(15)


if __name__ == "__main__":
    main()

# ==========================================
# Strategy: "Triple-Confirmation Trend Rider"
#
# A trade is only taken when ALL of these agree:
#   1. TREND   — price above EMA200 on the higher timeframe (longs)
#                or below it (shorts, forex only)
#   2. TRIGGER — EMA9 crosses EMA21 in the trend direction on the
#                entry timeframe (fresh cross, last 3 candles)
#   3. MOMENTUM— RSI(14) in the healthy zone (not chasing tops/bottoms)
#                and MACD histogram rising (longs) / falling (shorts)
#
# SL / TP are set automatically from market volatility (ATR):
#   SL = 1.5 x ATR   |   TP = 3 x ATR   (1 : 2 risk-reward)
#   + breakeven move after +1 x ATR
#   + chandelier trailing stop at 2 x ATR from the peak
# ==========================================

import config
from indicators import atr, ema, macd, rsi


def analyze(candles, trend_candles, allow_short=False):
    """
    candles       : entry-timeframe candles (oldest -> newest)
    trend_candles : higher-timeframe candles for the EMA200 trend filter
    allow_short   : shorts allowed (forex); crypto spot is long-only

    Returns dict {side, price, atr, reason} or None if no signal.
    """
    need = max(config.EMA_TREND, config.ATR_PERIOD + 1, 40)
    if len(candles) < need or len(trend_candles) < config.EMA_TREND:
        return None

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    price = closes[-1]

    # --- 1. Higher-timeframe trend filter ---
    trend_closes = [c["close"] for c in trend_candles]
    ema_trend = ema(trend_closes, config.EMA_TREND)[-1]
    if ema_trend is None:
        return None
    uptrend = trend_closes[-1] > ema_trend
    downtrend = trend_closes[-1] < ema_trend

    # --- 2. EMA crossover trigger (fresh cross within last 3 candles) ---
    ema_fast = ema(closes, config.EMA_FAST)
    ema_slow = ema(closes, config.EMA_SLOW)

    def crossed(direction):
        for i in range(-3, 0):
            f0, s0 = ema_fast[i - 1], ema_slow[i - 1]
            f1, s1 = ema_fast[i], ema_slow[i]
            if None in (f0, s0, f1, s1):
                continue
            if direction == "long" and f0 <= s0 and f1 > s1:
                return True
            if direction == "short" and f0 >= s0 and f1 < s1:
                return True
        return False

    # --- 3. Momentum confirmation ---
    rsi_val = rsi(closes, config.RSI_PERIOD)[-1]
    _, _, hist = macd(closes)
    if rsi_val is None or hist[-1] is None or hist[-2] is None:
        return None

    atr_val = atr(highs, lows, closes, config.ATR_PERIOD)[-1]
    if not atr_val or atr_val <= 0:
        return None

    if (
        uptrend
        and crossed("long")
        and config.RSI_LONG_MIN <= rsi_val <= config.RSI_LONG_MAX
        and hist[-1] > hist[-2]
    ):
        return {
            "side": "long",
            "price": price,
            "atr": atr_val,
            "reason": (
                f"Uptrend (>EMA{config.EMA_TREND}) + EMA{config.EMA_FAST}/"
                f"{config.EMA_SLOW} bull cross + RSI {rsi_val:.1f} + MACD rising"
            ),
        }

    if (
        allow_short
        and downtrend
        and crossed("short")
        and config.RSI_SHORT_MIN <= rsi_val <= config.RSI_SHORT_MAX
        and hist[-1] < hist[-2]
    ):
        return {
            "side": "short",
            "price": price,
            "atr": atr_val,
            "reason": (
                f"Downtrend (<EMA{config.EMA_TREND}) + EMA{config.EMA_FAST}/"
                f"{config.EMA_SLOW} bear cross + RSI {rsi_val:.1f} + MACD falling"
            ),
        }

    return None


def make_levels(side, entry, atr_val):
    """Automatic SL / TP / trailing levels from volatility."""
    if side == "long":
        sl = entry - config.SL_ATR_MULT * atr_val
        tp = entry + config.TP_ATR_MULT * atr_val
    else:
        sl = entry + config.SL_ATR_MULT * atr_val
        tp = entry - config.TP_ATR_MULT * atr_val
    return sl, tp


def update_stop(trade, price):
    """
    Manage an open trade's stop:
      - move SL to breakeven after +1 x ATR of profit
      - chandelier trail: 2 x ATR behind the best price seen
    Mutates trade dict; returns the (possibly improved) stop.
    """
    a = trade["atr"]
    if trade["side"] == "long":
        trade["peak"] = max(trade["peak"], price)
        if not trade["breakeven"] and price >= trade["entry"] + config.BREAKEVEN_ATR * a:
            trade["sl"] = max(trade["sl"], trade["entry"])
            trade["breakeven"] = True
        trail = trade["peak"] - config.TRAIL_ATR_MULT * a
        if trade["breakeven"]:
            trade["sl"] = max(trade["sl"], trail)
    else:
        trade["peak"] = min(trade["peak"], price)
        if not trade["breakeven"] and price <= trade["entry"] - config.BREAKEVEN_ATR * a:
            trade["sl"] = min(trade["sl"], trade["entry"])
            trade["breakeven"] = True
        trail = trade["peak"] + config.TRAIL_ATR_MULT * a
        if trade["breakeven"]:
            trade["sl"] = min(trade["sl"], trail)
    return trade["sl"]


def check_exit(trade, price):
    """Returns exit reason string or None."""
    if trade["side"] == "long":
        if price <= trade["sl"]:
            return "STOP LOSS" if not trade["breakeven"] else "TRAILING STOP"
        if price >= trade["tp"]:
            return "TARGET HIT"
    else:
        if price >= trade["sl"]:
            return "STOP LOSS" if not trade["breakeven"] else "TRAILING STOP"
        if price <= trade["tp"]:
            return "TARGET HIT"
    return None

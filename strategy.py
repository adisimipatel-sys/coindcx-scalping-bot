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

import statistics

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


def make_levels(side, entry, atr_val, sl_mult=None, tp_mult=None):
    """Automatic SL / TP / trailing levels from volatility."""
    sl_mult = config.SL_ATR_MULT if sl_mult is None else sl_mult
    tp_mult = config.TP_ATR_MULT if tp_mult is None else tp_mult
    if side == "long":
        sl = entry - sl_mult * atr_val
        tp = entry + tp_mult * atr_val
    else:
        sl = entry + sl_mult * atr_val
        tp = entry - tp_mult * atr_val
    return sl, tp


def update_stop(trade, price):
    """
    Manage an open trade's stop:
      - move SL to breakeven after +BREAKEVEN_ATR x ATR of profit
      - chandelier trail: TRAIL_ATR_MULT x ATR behind the best price seen
    Per-trade overrides via trade["be_atr"] / trade["trail_mult"];
    trade["be_atr"] = None disables breakeven+trailing entirely.
    Mutates trade dict; returns the (possibly improved) stop.
    """
    a = trade["atr"]
    be_atr = trade.get("be_atr", config.BREAKEVEN_ATR)
    trail_mult = trade.get("trail_mult", config.TRAIL_ATR_MULT)
    if be_atr is None or trail_mult is None:
        return trade["sl"]
    if trade["side"] == "long":
        trade["peak"] = max(trade["peak"], price)
        if not trade["breakeven"] and price >= trade["entry"] + be_atr * a:
            trade["sl"] = max(trade["sl"], trade["entry"])
            trade["breakeven"] = True
        trail = trade["peak"] - trail_mult * a
        if trade["breakeven"]:
            trade["sl"] = max(trade["sl"], trail)
    else:
        trade["peak"] = min(trade["peak"], price)
        if not trade["breakeven"] and price <= trade["entry"] - be_atr * a:
            trade["sl"] = min(trade["sl"], trade["entry"])
            trade["breakeven"] = True
        trail = trade["peak"] + trail_mult * a
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


# ==========================================
# Alternative strategies (compare with strategy_lab.py; select via
# STRATEGY in .env — see config.STRATEGY)
# ==========================================

def _base(candles, trend_candles):
    """Shared prep: returns (closes, highs, lows, price, uptrend, downtrend, atr)."""
    if len(candles) < 220 or len(trend_candles) < config.EMA_TREND:
        return None
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    trend_closes = [c["close"] for c in trend_candles]
    ema_trend = ema(trend_closes, config.EMA_TREND)[-1]
    if ema_trend is None:
        return None
    atr_val = atr(highs, lows, closes, config.ATR_PERIOD)[-1]
    if not atr_val or atr_val <= 0:
        return None
    return (closes, highs, lows, closes[-1],
            trend_closes[-1] > ema_trend, trend_closes[-1] < ema_trend, atr_val)


def analyze_rsi2(candles, trend_candles, allow_short=False):
    """Connors RSI(2): deep pullback inside an established trend."""
    b = _base(candles, trend_candles)
    if not b:
        return None
    closes, _, _, price, up, down, atr_val = b
    r2 = rsi(closes, 2)[-1]
    if r2 is None:
        return None
    if up and r2 < 10:
        return {"side": "long", "price": price, "atr": atr_val,
                "reason": f"Uptrend + RSI(2)={r2:.0f} deep dip"}
    if allow_short and down and r2 > 90:
        return {"side": "short", "price": price, "atr": atr_val,
                "reason": f"Downtrend + RSI(2)={r2:.0f} spike"}
    return None


def analyze_ema_pullback(candles, trend_candles, allow_short=False):
    """Buy a controlled dip to EMA21 in an uptrend that is turning back up."""
    b = _base(candles, trend_candles)
    if not b:
        return None
    closes, _, _, price, up, down, atr_val = b
    e21 = ema(closes, 21)[-1]
    r14 = rsi(closes, config.RSI_PERIOD)[-1]
    if e21 is None or r14 is None:
        return None
    near = abs(price - e21) <= 0.3 * atr_val
    turning_up = closes[-1] > closes[-2] > 0
    turning_dn = closes[-1] < closes[-2]
    if up and near and turning_up and 35 <= r14 <= 55:
        return {"side": "long", "price": price, "atr": atr_val,
                "reason": f"Uptrend pullback to EMA21, RSI {r14:.0f}, turning up"}
    if allow_short and down and near and turning_dn and 45 <= r14 <= 65:
        return {"side": "short", "price": price, "atr": atr_val,
                "reason": f"Downtrend rally to EMA21, RSI {r14:.0f}, turning down"}
    return None


def analyze_bb_reversion(candles, trend_candles, allow_short=False):
    """Bollinger(20,2) band touch against the move, traded with the trend."""
    b = _base(candles, trend_candles)
    if not b:
        return None
    closes, _, _, price, up, down, atr_val = b
    window = closes[-20:]
    mid = sum(window) / 20
    sd = statistics.pstdev(window)
    if sd <= 0:
        return None
    lower, upper = mid - 2 * sd, mid + 2 * sd
    if up and price <= lower:
        return {"side": "long", "price": price, "atr": atr_val,
                "reason": "Uptrend + close below lower Bollinger band"}
    if allow_short and down and price >= upper:
        return {"side": "short", "price": price, "atr": atr_val,
                "reason": "Downtrend + close above upper Bollinger band"}
    return None


def connors_exit(trade, window_candles, bars_held):
    """Original Connors exit: leave on strength (RSI2 recovers), or time-stop."""
    closes = [c["close"] for c in window_candles]
    r2 = rsi(closes, 2)[-1]
    if r2 is None:
        return None
    if trade["side"] == "long" and r2 > 65:
        return "RSI STRENGTH EXIT"
    if trade["side"] == "short" and r2 < 35:
        return "RSI STRENGTH EXIT"
    if bars_held >= 10:
        return "TIME EXIT"
    return None


VARIANTS = {
    # name: (analyze_fn, params {sl, tp, trail, be})
    "trend_rider":  (analyze, {"sl": 1.5, "tp": 3.0, "trail": 2.0, "be": 1.0}),
    "trend_rr1":    (analyze, {"sl": 1.5, "tp": 1.5, "trail": None, "be": None}),
    "rsi2_dip":     (analyze_rsi2, {"sl": 2.5, "tp": 1.0, "trail": None, "be": None}),
    "rsi2_connors": (analyze_rsi2, {"sl": 3.0, "tp": 10.0, "trail": None, "be": None,
                                    "exit_fn": connors_exit}),
    "rsi2_tight":   (analyze_rsi2, {"sl": 2.0, "tp": 1.5, "trail": None, "be": None}),
    "ema_pullback": (analyze_ema_pullback, {"sl": 1.5, "tp": 1.5, "trail": None, "be": None}),
    "bb_reversion": (analyze_bb_reversion, {"sl": 2.0, "tp": 1.5, "trail": None, "be": None}),
}


def get_strategy(name=None):
    """Return (analyze_fn, params) for the configured strategy."""
    name = name or config.STRATEGY
    if name not in VARIANTS:
        raise ValueError(f"Unknown STRATEGY '{name}'. Options: {', '.join(VARIANTS)}")
    return VARIANTS[name]

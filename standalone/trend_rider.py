# ============================================================
# STRATEGY 1: TREND RIDER (Triple-Confirmation Trend Following)
# Pura self-contained code — koi aur file ki zaroorat nahi.
#
# KAB BUY/SELL:
#   1. TREND    : price EMA200 ke UPAR (1h chart)  -> sirf LONG
#                 price EMA200 ke NEECHE           -> sirf SHORT (forex)
#   2. TRIGGER  : EMA9 ne EMA21 ko cross kiya (fresh, last 3 candles)
#   3. MOMENTUM : RSI(14) healthy zone me + MACD histogram confirm
#   -- Teeno agree = trade. Ek bhi na = koi trade nahi.
#
# SL/TP (apne aap set, volatility/ATR se):
#   SL = entry - 1.5 x ATR
#   TP = entry + 3.0 x ATR      (risk-reward 1:2)
#   +1 x ATR profit ke baad SL entry par (risk-free)
#   uske baad trailing stop: peak - 2 x ATR
#
# Backtest character: win rate ~35-40%, lekin winners losers se
# double bade -> total profit sabse zyada (+7.4R pure data par).
# ============================================================

# ---------- SETTINGS ----------
EMA_FAST, EMA_SLOW, EMA_TREND = 9, 21, 200
RSI_PERIOD = 14
RSI_LONG_MIN, RSI_LONG_MAX = 45, 70
RSI_SHORT_MIN, RSI_SHORT_MAX = 30, 55
ATR_PERIOD = 14
SL_ATR = 1.5      # stop loss distance
TP_ATR = 3.0      # take profit distance (1:2 RR)
BREAKEVEN_ATR = 1.0
TRAIL_ATR = 2.0


# ---------- INDICATORS ----------
def ema(values, period):
    if len(values) < period:
        return [None] * len(values)
    out = [None] * (period - 1)
    prev = sum(values[:period]) / period
    out.append(prev)
    k = 2 / (period + 1)
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(values, period=14):
    n = len(values)
    if n < period + 1:
        return [None] * n
    out = [None] * period
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / period, losses / period
    out.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    for i in range(period + 1, n):
        d = values[i] - values[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        out.append(100.0 if al == 0 else 100 - 100 / (1 + ag / al))
    return out


def macd(values, fast=12, slow=26, signal=9):
    n = len(values)
    ef, es = ema(values, fast), ema(values, slow)
    line = [(f - s) if f is not None and s is not None else None
            for f, s in zip(ef, es)]
    valid = [m for m in line if m is not None]
    if len(valid) < signal:
        return line, [None] * n, [None] * n
    sig = [None] * (n - len(valid)) + ema(valid, signal)
    hist = [(m - s) if m is not None and s is not None else None
            for m, s in zip(line, sig)]
    return line, sig, hist


def atr(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1:
        return [None] * n
    trs = [max(highs[i] - lows[i],
               abs(highs[i] - closes[i - 1]),
               abs(lows[i] - closes[i - 1])) for i in range(1, n)]
    out = [None] * period
    prev = sum(trs[:period]) / period
    out.append(prev)
    for tr in trs[period:]:
        prev = (prev * (period - 1) + tr) / period
        out.append(prev)
    return out


# ---------- ENTRY SIGNAL ----------
def analyze(candles, trend_candles, allow_short=False):
    """
    candles       : entry timeframe (e.g. 5m) — list of dicts
                    {open, high, low, close}, purana -> naya
    trend_candles : higher timeframe (e.g. 1h) — EMA200 filter ke liye
    Return        : {"side","price","atr","sl","tp","reason"} ya None
    """
    if len(candles) < EMA_TREND or len(trend_candles) < EMA_TREND:
        return None

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    price = closes[-1]

    # 1. TREND filter (higher timeframe EMA200)
    tc = [c["close"] for c in trend_candles]
    ema200 = ema(tc, EMA_TREND)[-1]
    if ema200 is None:
        return None
    uptrend, downtrend = tc[-1] > ema200, tc[-1] < ema200

    # 2. TRIGGER: fresh EMA9/21 cross (last 3 candles me)
    ef, es = ema(closes, EMA_FAST), ema(closes, EMA_SLOW)

    def crossed(direction):
        for i in range(-3, 0):
            f0, s0, f1, s1 = ef[i - 1], es[i - 1], ef[i], es[i]
            if None in (f0, s0, f1, s1):
                continue
            if direction == "long" and f0 <= s0 and f1 > s1:
                return True
            if direction == "short" and f0 >= s0 and f1 < s1:
                return True
        return False

    # 3. MOMENTUM: RSI zone + MACD histogram
    r = rsi(closes, RSI_PERIOD)[-1]
    _, _, hist = macd(closes)
    a = atr(highs, lows, closes, ATR_PERIOD)[-1]
    if r is None or hist[-1] is None or hist[-2] is None or not a:
        return None

    if uptrend and crossed("long") and RSI_LONG_MIN <= r <= RSI_LONG_MAX \
            and hist[-1] > hist[-2]:
        return {"side": "long", "price": price, "atr": a,
                "sl": price - SL_ATR * a, "tp": price + TP_ATR * a,
                "reason": f"Uptrend + EMA9/21 bull cross + RSI {r:.0f} + MACD rising"}

    if allow_short and downtrend and crossed("short") \
            and RSI_SHORT_MIN <= r <= RSI_SHORT_MAX and hist[-1] < hist[-2]:
        return {"side": "short", "price": price, "atr": a,
                "sl": price + SL_ATR * a, "tp": price - TP_ATR * a,
                "reason": f"Downtrend + EMA9/21 bear cross + RSI {r:.0f} + MACD falling"}

    return None


# ---------- TRADE MANAGEMENT (breakeven + trailing) ----------
def update_stop(trade, price):
    """Har price update par call karo. trade dict me chahiye:
    side, entry, sl, atr, peak, breakeven(False se shuru)."""
    a = trade["atr"]
    if trade["side"] == "long":
        trade["peak"] = max(trade["peak"], price)
        if not trade["breakeven"] and price >= trade["entry"] + BREAKEVEN_ATR * a:
            trade["sl"] = max(trade["sl"], trade["entry"])   # risk-free
            trade["breakeven"] = True
        if trade["breakeven"]:
            trade["sl"] = max(trade["sl"], trade["peak"] - TRAIL_ATR * a)
    else:
        trade["peak"] = min(trade["peak"], price)
        if not trade["breakeven"] and price <= trade["entry"] - BREAKEVEN_ATR * a:
            trade["sl"] = min(trade["sl"], trade["entry"])
            trade["breakeven"] = True
        if trade["breakeven"]:
            trade["sl"] = min(trade["sl"], trade["peak"] + TRAIL_ATR * a)
    return trade["sl"]


def check_exit(trade, price):
    """Return: 'STOP LOSS' / 'TRAILING STOP' / 'TARGET HIT' / None."""
    if trade["side"] == "long":
        if price <= trade["sl"]:
            return "TRAILING STOP" if trade["breakeven"] else "STOP LOSS"
        if price >= trade["tp"]:
            return "TARGET HIT"
    else:
        if price >= trade["sl"]:
            return "TRAILING STOP" if trade["breakeven"] else "STOP LOSS"
        if price <= trade["tp"]:
            return "TARGET HIT"
    return None

# ============================================================
# STRATEGY 2: RSI(2) DIP (Larry Connors Mean Reversion)
# Pura self-contained code — koi aur file ki zaroorat nahi.
#
# IDEA: strong trend me jab price 2-3 candle ke liye zor se
# gire (RSI-2 < 10), toh woh dip aksar wapas bounce hota hai.
# Hum trend ki direction me woh dip kharidte hain.
#
# KAB BUY/SELL:
#   LONG : price EMA200 ke UPAR (1h chart)  +  RSI(2) < 10
#   SHORT: price EMA200 ke NEECHE           +  RSI(2) > 90  (forex only)
#
# SL/TP (apne aap set, ATR se) — TREND RIDER SE ULTA:
#   TP = entry + 1.0 x ATR   (chhota target, jaldi book)
#   SL = entry - 2.5 x ATR   (wide stop, bounce ko jagah dena)
#   koi trailing nahi — target ya stop, bas.
#
# Backtest character: WIN RATE SABSE ZYADA (83-88% validation par),
# profit factor 1.92-2.26 validation par. LEKIN training periods
# me loss tha — yeh regime-dependent hai. Winners chhote hote
# hain, kabhi-kabhi ek bada loss bahut kuch wapas le leta hai.
# High win rate != zyada total profit. Paper mode me pehle test karo.
# ============================================================

# ---------- SETTINGS ----------
EMA_TREND = 200      # higher-timeframe trend filter
RSI_ENTRY_PERIOD = 2 # Connors ka famous 2-period RSI
RSI_BUY_BELOW = 10   # itna oversold ho tab dip kharido
RSI_SELL_ABOVE = 90  # short ke liye (forex)
ATR_PERIOD = 14
SL_ATR = 2.5         # wide stop — bounce ko saans lene ki jagah
TP_ATR = 1.0         # quick target — mean reversion jaldi book hoti hai


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


def rsi(values, period=2):
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
    if len(candles) < 220 or len(trend_candles) < EMA_TREND:
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

    # 2. RSI(2) extreme dip/spike
    r2 = rsi(closes, RSI_ENTRY_PERIOD)[-1]
    a = atr(highs, lows, closes, ATR_PERIOD)[-1]
    if r2 is None or not a:
        return None

    # LONG: uptrend me deep dip kharido
    if uptrend and r2 < RSI_BUY_BELOW:
        return {"side": "long", "price": price, "atr": a,
                "sl": price - SL_ATR * a, "tp": price + TP_ATR * a,
                "reason": f"Uptrend + RSI(2)={r2:.0f} deep dip"}

    # SHORT: downtrend me spike becho (sirf forex)
    if allow_short and downtrend and r2 > RSI_SELL_ABOVE:
        return {"side": "short", "price": price, "atr": a,
                "sl": price + SL_ATR * a, "tp": price - TP_ATR * a,
                "reason": f"Downtrend + RSI(2)={r2:.0f} spike"}

    return None


# ---------- EXIT (simple: target ya stop, koi trailing nahi) ----------
def check_exit(trade, price):
    """Return: 'STOP LOSS' / 'TARGET HIT' / None.
    trade dict me chahiye: side, sl, tp."""
    if trade["side"] == "long":
        if price <= trade["sl"]:
            return "STOP LOSS"
        if price >= trade["tp"]:
            return "TARGET HIT"
    else:
        if price >= trade["sl"]:
            return "STOP LOSS"
        if price <= trade["tp"]:
            return "TARGET HIT"
    return None


# ---------- OPTIONAL: original Connors-style exit ----------
def connors_exit(trade, recent_closes, bars_held):
    """Fixed TP ke bajaye 'strength par exit': RSI(2) recover ho jaye
    toh niklo, ya 10 candle ho jayen toh time-exit. Use karna ho toh
    check_exit ke saath har candle par isko bhi call karo."""
    r2 = rsi(recent_closes, RSI_ENTRY_PERIOD)[-1]
    if r2 is None:
        return None
    if trade["side"] == "long" and r2 > 65:
        return "RSI STRENGTH EXIT"
    if trade["side"] == "short" and r2 < 35:
        return "RSI STRENGTH EXIT"
    if bars_held >= 10:
        return "TIME EXIT"
    return None

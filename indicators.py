# ==========================================
# Technical indicators — pure Python, no heavy dependencies.
# All functions take a list of floats (oldest -> newest) and
# return a list of the same length (None where not enough data).
# ==========================================


def ema(values, period):
    if len(values) < period:
        return [None] * len(values)
    out = [None] * (period - 1)
    sma = sum(values[:period]) / period
    out.append(sma)
    k = 2 / (period + 1)
    prev = sma
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi(values, period=14):
    """Wilder's RSI."""
    n = len(values)
    if n < period + 1:
        return [None] * n
    out = [None] * period
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_gain, avg_loss = gains / period, losses / period
    out.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    for i in range(period + 1, n):
        d = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-d, 0)) / period
        out.append(100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss))
    return out


def macd(values, fast=12, slow=26, signal=9):
    """Returns (macd_line, signal_line, histogram) lists."""
    n = len(values)
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    valid = [m for m in macd_line if m is not None]
    if len(valid) < signal:
        return macd_line, [None] * n, [None] * n
    sig_valid = ema(valid, signal)
    pad = n - len(valid)
    signal_line = [None] * pad + sig_valid
    hist = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, hist


def atr(highs, lows, closes, period=14):
    """Wilder's Average True Range."""
    n = len(closes)
    if n < period + 1:
        return [None] * n
    trs = []
    for i in range(1, n):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    out = [None] * period
    prev = sum(trs[:period]) / period
    out.append(prev)
    for tr in trs[period:]:
        prev = (prev * (period - 1) + tr) / period
        out.append(prev)
    return out

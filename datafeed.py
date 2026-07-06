# ==========================================
# Market data feeds:
#   - Crypto: CoinDCX public candles API
#   - Forex : Yahoo Finance chart API (free, no key needed)
# Candles are returned as dicts: {time, open, high, low, close}
# oldest -> newest.
# ==========================================

import time

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (trading-bot)"}

# cache: CoinDCX symbol ("BTCINR") -> candle pair ("I-BTC_INR")
_pair_cache = {}
_pair_cache_time = 0


def _coindcx_pair(symbol):
    """Map a CoinDCX market symbol to its candle-API pair name."""
    global _pair_cache, _pair_cache_time
    if not _pair_cache or time.time() - _pair_cache_time > 3600:
        r = requests.get(
            "https://api.coindcx.com/exchange/v1/markets_details",
            headers=HEADERS, timeout=15,
        )
        r.raise_for_status()
        _pair_cache = {m["symbol"]: m["pair"] for m in r.json() if m.get("pair")}
        _pair_cache_time = time.time()
    return _pair_cache.get(symbol)


def crypto_candles(symbol, interval="5m", limit=300):
    """Fetch OHLC candles for a CoinDCX market like 'BTCINR'."""
    pair = _coindcx_pair(symbol)
    if not pair:
        return []
    r = requests.get(
        "https://public.coindcx.com/market_data/candles",
        params={"pair": pair, "interval": interval, "limit": limit},
        headers=HEADERS, timeout=15,
    )
    r.raise_for_status()
    raw = r.json()
    if not isinstance(raw, list):
        return []
    candles = [
        {
            "time": c["time"],
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"]),
        }
        for c in raw
        if c.get("close") is not None
    ]
    candles.sort(key=lambda c: c["time"])
    return candles[-limit:]


_YAHOO_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m", "1d": "1d"}
_YAHOO_RANGE = {"1m": "1d", "5m": "5d", "15m": "5d", "30m": "1mo", "1h": "1mo", "1d": "1y"}


def forex_candles(symbol, interval="5m", limit=300):
    """Fetch OHLC candles for a forex pair like 'EURUSD' from Yahoo Finance."""
    yi = _YAHOO_INTERVAL.get(interval, "5m")
    rng = _YAHOO_RANGE.get(interval, "5d")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}=X"
    r = requests.get(
        url,
        params={"interval": yi, "range": rng},
        headers=HEADERS, timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        return []
    ts = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    candles = []
    for i, t in enumerate(ts):
        o, h, l, c = (
            quote.get("open", [None])[i] if i < len(quote.get("open", [])) else None,
            quote.get("high", [None])[i] if i < len(quote.get("high", [])) else None,
            quote.get("low", [None])[i] if i < len(quote.get("low", [])) else None,
            quote.get("close", [None])[i] if i < len(quote.get("close", [])) else None,
        )
        if None in (o, h, l, c):
            continue
        candles.append({"time": t * 1000, "open": o, "high": h, "low": l, "close": c})
    return candles[-limit:]


def get_candles(symbol, market, interval="5m", limit=300):
    """market: 'crypto' or 'forex'."""
    if market == "crypto":
        return crypto_candles(symbol, interval, limit)
    return forex_candles(symbol, interval, limit)

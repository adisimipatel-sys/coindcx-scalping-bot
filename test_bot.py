# ==========================================
# Offline tests — run with:  python test_bot.py
# No network needed; uses synthetic candles.
# ==========================================

import math
import random

import config
import strategy
from indicators import atr, ema, macd, rsi


def make_candles(closes, spread=0.5):
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append({
            "time": i, "open": o,
            "high": max(o, c) + spread, "low": min(o, c) - spread,
            "close": c,
        })
    return out


def test_indicators():
    vals = list(range(1, 51))  # 1..50
    e = ema([float(v) for v in vals], 10)
    assert e[8] is None and e[9] == 5.5, "EMA seed should be SMA of first 10"
    assert 44 < e[-1] < 50, f"EMA of rising series should trail price: {e[-1]}"

    r = rsi([float(v) for v in vals], 14)
    assert r[-1] == 100, "RSI of always-rising series must be 100"
    r2 = rsi([float(v) for v in reversed(vals)], 14)
    assert r2[-1] == 0, "RSI of always-falling series must be 0"

    m, s, h = macd([float(v) for v in vals])
    assert m[-1] is not None and s[-1] is not None and h[-1] is not None

    c = make_candles([100.0 + 0.1 * i for i in range(30)], spread=1.0)
    a = atr([x["high"] for x in c], [x["low"] for x in c], [x["close"] for x in c], 14)
    assert a[-1] is not None and a[-1] > 0
    print("✅ indicators OK")


def trending_candles(n=350, start=100.0, drift=0.15, seed=7):
    """Uptrend with noise + a fresh dip-and-cross near the end."""
    random.seed(seed)
    closes, price = [], start
    for i in range(n):
        price += drift + random.uniform(-0.4, 0.4)
        closes.append(price)
    # pullback then recovery to force a fresh EMA9/21 bull cross with healthy RSI
    for i in range(16):
        closes.append(closes[-1] - 0.3)
    for i in range(7):
        closes.append(closes[-1] + 0.6)
    return make_candles(closes)


def test_strategy_signal():
    candles = trending_candles()
    trend = make_candles([50.0 + 0.5 * i for i in range(config.EMA_TREND + 10)])
    sig = strategy.analyze(candles, trend, allow_short=False)
    assert sig is not None, "expected a long signal on trending data with fresh cross"
    assert sig["side"] == "long" and sig["atr"] > 0
    print(f"✅ strategy signal OK: {sig['reason']}")

    # downtrend must block longs
    trend_dn = make_candles([500.0 - 0.5 * i for i in range(config.EMA_TREND + 10)])
    assert strategy.analyze(candles, trend_dn, allow_short=False) is None
    print("✅ trend filter blocks counter-trend trades")


def test_levels_and_exits():
    entry, a = 100.0, 2.0
    sl, tp = strategy.make_levels("long", entry, a)
    assert math.isclose(sl, 97.0) and math.isclose(tp, 106.0), (sl, tp)
    rr = (tp - entry) / (entry - sl)
    assert math.isclose(rr, 2.0), "risk-reward must be 1:2"

    trade = {"side": "long", "entry": entry, "sl": sl, "tp": tp,
             "atr": a, "peak": entry, "breakeven": False}

    # fresh trade: SL and TP hits detected
    assert strategy.check_exit(trade, tp) == "TARGET HIT"
    assert strategy.check_exit(trade, sl - 0.01) == "STOP LOSS"

    # not yet at breakeven trigger
    strategy.update_stop(trade, 101.0)
    assert not trade["breakeven"] and trade["sl"] == sl

    # +1 ATR -> breakeven
    strategy.update_stop(trade, 102.0)
    assert trade["breakeven"] and trade["sl"] >= entry

    # big run -> chandelier trail locks profit
    strategy.update_stop(trade, 110.0)
    assert trade["sl"] >= 110.0 - config.TRAIL_ATR_MULT * a
    assert strategy.check_exit(trade, trade["sl"] - 0.01) == "TRAILING STOP"

    # short side
    ssl, stp = strategy.make_levels("short", entry, a)
    assert math.isclose(ssl, 103.0) and math.isclose(stp, 94.0)
    st = {"side": "short", "entry": entry, "sl": ssl, "tp": stp,
          "atr": a, "peak": entry, "breakeven": False}
    strategy.update_stop(st, 98.0)
    assert st["breakeven"] and st["sl"] <= entry
    assert strategy.check_exit(st, stp) == "TARGET HIT"
    print("✅ SL/TP, breakeven, trailing, exits OK")


def test_paper_trade_flow():
    import bot
    bot.balance = 2000.0
    sig = {"side": "long", "price": 100.0, "atr": 2.0, "reason": "test"}
    bot.enter_trade("TESTINR", "crypto", sig)
    assert "TESTINR" in bot.open_trades
    t = bot.open_trades["TESTINR"]
    # 1% risk of 2000 = 20; per-unit risk = 3 -> qty ~6.67, capped at 25% notional (5.0)
    assert t["qty"] <= (2000 * 0.25) / 100.0 + 1e-9
    assert t["mode"] == "PAPER"

    bot.exit_trade("TESTINR", "TARGET HIT", t["tp"])
    assert "TESTINR" not in bot.open_trades
    assert bot.balance > 2000.0, "TP exit must be profitable"
    assert not bot.can_trade("TESTINR"), "cooldown must block instant re-entry"
    print(f"✅ paper trade flow OK (balance 2000 -> {bot.balance:.2f})")


if __name__ == "__main__":
    test_indicators()
    test_strategy_signal()
    test_levels_and_exits()
    test_paper_trade_flow()
    print("\n🎉 All tests passed")

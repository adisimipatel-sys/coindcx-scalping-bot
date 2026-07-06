# ==========================================
# Backtester — runs the EXACT same strategy code the live bot uses
# (strategy.analyze / make_levels / update_stop / check_exit).
#
# Usage:
#   python backtest.py --sample          # offline: real EURUSD hourly + GOOG
#                                        # daily bundled with the `backtesting`
#                                        # package (pip install backtesting)
#   python backtest.py                   # live data: fetches your crypto +
#                                        # forex watchlists via datafeed.py
#
# Honest-simulation rules:
#   - signals only on CLOSED candles (no lookahead)
#   - higher-timeframe trend candles resampled from entry candles,
#     including the still-forming one (exactly what the live bot sees)
#   - SL/TP checked against each bar's high/low; if BOTH could hit in
#     the same bar, the STOP is assumed to hit first (pessimistic)
#   - fees/spread charged on every entry and exit
#   - position sizing identical to the bot: 1% equity risk, 25% notional cap
# ==========================================

import argparse
import math

import config
import strategy

ENTRY_WINDOW = 600   # bars passed to analyze() (needs >= EMA_TREND)
TREND_FACTOR = 12    # entry bars per trend bar (mirrors 5m -> 1h)


def resample(candles, factor):
    """Group entry candles into higher-timeframe candles (last one may be partial)."""
    out = []
    for i in range(0, len(candles), factor):
        chunk = candles[i:i + factor]
        out.append({
            "time": chunk[0]["time"],
            "open": chunk[0]["open"],
            "high": max(c["high"] for c in chunk),
            "low": min(c["low"] for c in chunk),
            "close": chunk[-1]["close"],
        })
    return out


def run_backtest(name, candles, allow_short, fee_pct, start_balance=None,
                 trend_factor=TREND_FACTOR, analyze_fn=None, params=None,
                 quiet=False):
    """Walk-forward simulation. fee_pct = per-side cost (e.g. 0.002 = 0.2%).

    analyze_fn : signal function (default: the live bot's strategy.analyze)
    params     : optional dict {sl, tp, trail, be} of ATR multipliers;
                 trail/be = None disables trailing for this run
    """
    analyze_fn = analyze_fn or strategy.analyze
    exit_fn = params.get("exit_fn") if params else None
    balance = start_balance if start_balance is not None else config.START_BALANCE
    equity_curve = [balance]
    trades = []
    position = None
    cooldown_until = -1

    warmup = config.EMA_TREND * trend_factor  # trend EMA200 needs 200 trend bars
    if warmup >= len(candles) - 50:
        print(f"\n===== {name} =====\nNot enough data: need > {warmup + 50} bars, have {len(candles)}")
        return None
    cooldown_bars = max(1, math.ceil(config.COOLDOWN_MIN * 60_000 /
                                     max(candles[1]["time"] - candles[0]["time"], 1)))

    for i in range(warmup, len(candles)):
        bar = candles[i]

        # ---- manage open position (intrabar, pessimistic order) ----
        if position:
            p = position
            hit_sl = bar["low"] <= p["sl"] if p["side"] == "long" else bar["high"] >= p["sl"]
            hit_tp = bar["high"] >= p["tp"] if p["side"] == "long" else bar["low"] <= p["tp"]

            exit_price, reason = None, None
            if hit_sl:  # stop first when both touch (pessimistic)
                exit_price = p["sl"]
                reason = "TRAILING STOP" if p["breakeven"] else "STOP LOSS"
            elif hit_tp:
                exit_price, reason = p["tp"], "TARGET HIT"

            if exit_price is None and exit_fn:
                # strategy-specific exit (e.g. "exit on strength"), at bar close
                r2 = exit_fn(p, candles[max(0, i - 59):i + 1], i - p["bar"])
                if r2:
                    exit_price, reason = bar["close"], r2

            if exit_price is not None:
                direction = 1 if p["side"] == "long" else -1
                gross = (exit_price - p["entry"]) * direction * p["qty"]
                costs = fee_pct * p["qty"] * (p["entry"] + exit_price)
                pnl = gross - costs
                balance += pnl
                trades.append({
                    "side": p["side"], "entry": p["entry"], "exit": exit_price,
                    "pnl": pnl, "r": pnl / p["risk"] if p["risk"] else 0,
                    "reason": reason, "bars": i - p["bar"],
                })
                position = None
                cooldown_until = i + cooldown_bars
            else:
                # trail/breakeven update on bar close (bot does this every poll)
                strategy.update_stop(p, bar["close"])

        # ---- look for a new entry on this closed bar ----
        if position is None and i > cooldown_until:
            window = candles[max(0, i - ENTRY_WINDOW + 1):i + 1]
            trend = resample(candles[:i + 1], trend_factor)[-260:]
            sig = analyze_fn(window, trend, allow_short=allow_short)
            if sig:
                entry = sig["price"]
                sl_mult = params.get("sl") if params else None
                tp_mult = params.get("tp") if params else None
                sl, tp = strategy.make_levels(sig["side"], entry, sig["atr"],
                                              sl_mult, tp_mult)
                risk_amount = balance * config.RISK_PER_TRADE
                per_unit = abs(entry - sl)
                if per_unit > 0:
                    qty = min(risk_amount / per_unit, (balance * 0.25) / entry)
                    position = {
                        "side": sig["side"], "entry": entry, "qty": qty,
                        "sl": sl, "tp": tp, "atr": sig["atr"], "peak": entry,
                        "breakeven": False, "risk": qty * per_unit, "bar": i,
                    }
                    if params:
                        position["trail_mult"] = params.get("trail")
                        position["be_atr"] = params.get("be")

        equity_curve.append(balance)

    # close any position at the last price
    if position:
        p = position
        direction = 1 if p["side"] == "long" else -1
        exit_price = candles[-1]["close"]
        pnl = (exit_price - p["entry"]) * direction * p["qty"] \
            - fee_pct * p["qty"] * (p["entry"] + exit_price)
        balance += pnl
        trades.append({"side": p["side"], "entry": p["entry"], "exit": exit_price,
                       "pnl": pnl, "r": pnl / p["risk"] if p["risk"] else 0,
                       "reason": "END OF DATA", "bars": len(candles) - 1 - p["bar"]})
        equity_curve.append(balance)

    return report(name, trades, equity_curve, candles, warmup, quiet=quiet)


def report(name, trades, equity, candles, warmup, quiet=False):
    start = equity[0]
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in losses)

    peak, max_dd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak)

    bh = (candles[-1]["close"] - candles[warmup]["close"]) / candles[warmup]["close"]

    stats = {
        "name": name,
        "bars_tested": len(candles) - warmup,
        "trades": len(trades),
        "win_rate": 100 * len(wins) / len(trades) if trades else 0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "avg_r": sum(t["r"] for t in trades) / len(trades) if trades else 0,
        "net_return_pct": 100 * (equity[-1] - start) / start,
        "max_drawdown_pct": 100 * max_dd,
        "buy_hold_pct": 100 * bh,
        "final_balance": equity[-1],
    }

    if quiet:
        return stats

    print(f"\n===== {name} =====")
    print(f"Bars tested      : {stats['bars_tested']}")
    print(f"Trades           : {stats['trades']}  "
          f"(wins {len(wins)} / losses {len(losses)})")
    print(f"Win rate         : {stats['win_rate']:.1f}%")
    pf = stats["profit_factor"]
    print(f"Profit factor    : {'inf' if pf == float('inf') else f'{pf:.2f}'}")
    print(f"Avg R per trade  : {stats['avg_r']:+.2f}")
    print(f"Net return       : {stats['net_return_pct']:+.2f}%   "
          f"(buy & hold: {stats['buy_hold_pct']:+.2f}%)")
    print(f"Max drawdown     : {stats['max_drawdown_pct']:.2f}%")
    print(f"Final balance    : {stats['final_balance']:.2f} (start {start:.2f})")
    exits = {}
    for t in trades:
        exits[t["reason"]] = exits.get(t["reason"], 0) + 1
    if exits:
        print("Exit breakdown   : " + ", ".join(f"{k} x{v}" for k, v in sorted(exits.items())))
    return stats


def df_to_candles(df):
    return [
        {"time": int(ts.timestamp() * 1000), "open": float(r["Open"]),
         "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"])}
        for ts, r in df.iterrows()
    ]


def run_sample():
    """Backtest on REAL data bundled with the `backtesting` package."""
    from backtesting.test import EURUSD, GOOG

    print("Data: real EURUSD 1h (2017-2018) + real GOOG 1d (2004-2013)")
    print(f"Strategy config: SL {config.SL_ATR_MULT}xATR, TP {config.TP_ATR_MULT}xATR, "
          f"risk {config.RISK_PER_TRADE*100:.0f}%/trade\n")

    results = []
    # forex: longs + shorts, ~1 pip spread per side
    results.append(run_backtest("EURUSD 1h (forex, long+short)",
                                df_to_candles(EURUSD), allow_short=True, fee_pct=0.0001))
    # long-only trending asset (same regime as crypto spot), 0.2%/side fees,
    # weekly trend filter (factor 5) since data is daily
    results.append(run_backtest("GOOG 1d (long-only, crypto-spot style)",
                                df_to_candles(GOOG), allow_short=False,
                                fee_pct=0.002, trend_factor=5))
    return results


def run_live():
    """Backtest on live-fetched data (needs internet access to the data APIs)."""
    from datafeed import get_candles
    results = []
    for sym in config.CRYPTO_WATCHLIST:
        candles = get_candles(sym, "crypto", "5m", 3000)
        if len(candles) > config.EMA_TREND * TREND_FACTOR + 100:
            results.append(run_backtest(f"{sym} 5m (crypto)", candles,
                                        allow_short=False, fee_pct=0.002))
        else:
            print(f"{sym}: not enough candles ({len(candles)})")
    for sym in config.FOREX_WATCHLIST:
        candles = get_candles(sym, "forex", "1h", 3000)
        if len(candles) > config.EMA_TREND * TREND_FACTOR + 100:
            results.append(run_backtest(f"{sym} 1h (forex)", candles,
                                        allow_short=True, fee_pct=0.0001))
        else:
            print(f"{sym}: not enough candles ({len(candles)})")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true",
                    help="use real bundled sample data (works offline)")
    args = ap.parse_args()
    run_sample() if args.sample else run_live()

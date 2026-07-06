# ==========================================
# Strategy Lab — compare famous strategies on the SAME real data
# with a train/validation split (guards against overfitting:
# a strategy is only as good as its VALIDATION numbers).
#
# Usage:  pip install backtesting && python strategy_lab.py
#
# The strategy variants themselves live in strategy.py (VARIANTS) so the
# live bot can run any of them via STRATEGY in .env.
# ==========================================

import config
from backtest import TREND_FACTOR, df_to_candles, run_backtest
from strategy import VARIANTS


def split_runs(label, candles, allow_short, fee_pct, trend_factor):
    """Run every variant on train (first 65%) and validation (last 35%)."""
    warmup = config.EMA_TREND * trend_factor
    split = warmup + int((len(candles) - warmup) * 0.65)

    print(f"\n################ {label} ################")
    print(f"{'variant':<14} {'set':<6} {'trades':>6} {'win%':>6} {'PF':>6} "
          f"{'avgR':>6} {'net%':>7} {'maxDD%':>7}")

    results = {}
    for name, (fn, params) in VARIANTS.items():
        rows = []
        for set_name, data in (
            ("train", candles[:split]),
            ("valid", candles[split - warmup:]),  # warmup ends at the split point
        ):
            s = run_backtest(f"{label}/{name}/{set_name}", data, allow_short,
                             fee_pct, trend_factor=trend_factor,
                             analyze_fn=fn, params=params, quiet=True)
            if s is None:
                continue
            pf = s["profit_factor"]
            print(f"{name:<14} {set_name:<6} {s['trades']:>6} {s['win_rate']:>6.1f} "
                  f"{'inf' if pf == float('inf') else f'{pf:>6.2f}'} "
                  f"{s['avg_r']:>+6.2f} {s['net_return_pct']:>+7.2f} "
                  f"{s['max_drawdown_pct']:>7.2f}")
            rows.append(s)
        results[name] = rows
    return results


def main():
    from backtesting.test import EURUSD, GOOG

    all_results = {}
    all_results["EURUSD 1h"] = split_runs(
        "EURUSD 1h (forex, long+short)", df_to_candles(EURUSD),
        allow_short=True, fee_pct=0.0001, trend_factor=TREND_FACTOR)
    all_results["GOOG 1d"] = split_runs(
        "GOOG 1d (long-only)", df_to_candles(GOOG),
        allow_short=False, fee_pct=0.002, trend_factor=5)
    return all_results


if __name__ == "__main__":
    main()

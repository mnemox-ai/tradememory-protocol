"""Simplified h sensitivity: sync version, one combo at a time.

Usage: python research/level2/h_sensitivity_sync.py
"""
import json
import os
import sys
import time
import asyncio
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import Timeframe
from tradememory.simulation.agent import BaseAgent
from tradememory.simulation.simulator import Simulator
from tradememory.simulation.strategy_generator import generate_strategy_grid

sys.path.insert(0, os.path.dirname(__file__))
from cusum_agent import CUSUMOnlyAgent

import random
random.seed(42)

RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))
H_VALUES = [2.0, 3.0, 4.0, 5.0, 6.0]
MAX_STRATEGIES = 50
MIN_IS_TRADES = 30
IS_RATIO = 0.67
DAYS = 1095

COMBOS = [
    ("BTCUSDT", "1h", Timeframe.H1),
    ("BTCUSDT", "4h", Timeframe.H4),
    ("ETHUSDT", "1h", Timeframe.H1),
    ("ETHUSDT", "4h", Timeframe.H4),
]


async def fetch_data(symbol, tf_enum):
    ds = BinanceDataSource()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=DAYS)
    return await ds.fetch_ohlcv(symbol, tf_enum, start, end)


def main():
    all_strategies = generate_strategy_grid()
    print(f"Generated {len(all_strategies)} strategies", flush=True)

    h_results = {h: [] for h in H_VALUES}
    h_alert_rates = {h: [] for h in H_VALUES}

    for symbol, tf_str, tf_enum in COMBOS:
        print(f"\n{'='*60}", flush=True)
        print(f"{symbol} {tf_str}", flush=True)
        print(f"{'='*60}", flush=True)

        t0 = time.time()
        series = asyncio.run(fetch_data(symbol, tf_enum))
        print(f"  Fetched {len(series.bars)} bars in {time.time()-t0:.1f}s", flush=True)

        is_series, oos_series = series.split(IS_RATIO)

        # Qualify strategies
        qualified = []
        for strategy in all_strategies:
            base_is = BaseAgent(strategy, fixed_lot=0.01)
            r_is = Simulator(base_is, is_series, tf_str).run()
            if r_is.fitness.trade_count >= MIN_IS_TRADES:
                qualified.append((strategy, r_is))
            if len(qualified) >= MAX_STRATEGIES:
                break
        print(f"  Qualified: {len(qualified)}", flush=True)

        for j, (strategy, is_result) in enumerate(qualified):
            is_trades = is_result.trades

            # BaseAgent (same for all h)
            base = BaseAgent(strategy, fixed_lot=0.01)
            r_base = Simulator(base, oos_series, tf_str).run()
            base_dd = r_base.equity_max_dd

            # CUSUM with each h
            for h in H_VALUES:
                cusum = CUSUMOnlyAgent(strategy, fixed_lot=0.01, cusum_threshold=h)
                cusum.warm_start(is_trades)
                r_cusum = Simulator(cusum, oos_series, tf_str).run()

                dd_reduction = base_dd - r_cusum.equity_max_dd
                h_results[h].append(dd_reduction)

                reduced = getattr(cusum, '_reduced_count', 0)
                total = len(r_cusum.trades)
                h_alert_rates[h].append(reduced / max(total, 1))

            if (j + 1) % 10 == 0:
                print(f"    [{j+1}/{len(qualified)}]", flush=True)

        print(f"  Done {symbol} {tf_str} in {time.time()-t0:.1f}s", flush=True)

    # Print & save results
    print(f"\n{'='*70}", flush=True)
    print("H SENSITIVITY ANALYSIS", flush=True)
    print(f"{'='*70}", flush=True)
    print(f"{'h':>5} | {'Win Rate':>10} | {'Mean DD':>12} | {'Cohen d':>10} | {'p-value':>12} | {'Alert %':>10}", flush=True)
    print("-" * 70, flush=True)

    summary = {}
    for h in H_VALUES:
        diffs = h_results[h]
        n = len(diffs)
        m = mean(diffs)
        s = stdev(diffs) if n > 1 else 0.001
        wins = sum(1 for d in diffs if d > 0)
        d = m / s if s > 0 else 0
        t_stat, p_two = stats.ttest_1samp(diffs, 0)
        p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2
        avg_alert = mean(h_alert_rates[h])

        print(f"{h:5.1f} | {wins/n*100:9.1f}% | {m:+11.2f} | {d:9.4f} | {p_one:11.6f} | {avg_alert*100:9.1f}%", flush=True)
        summary[str(h)] = {
            "n": n, "win_rate": round(wins/n, 4),
            "mean_dd_reduction": round(m, 2), "cohens_d": round(d, 4),
            "p_one_sided": round(p_one, 6), "avg_alert_rate": round(avg_alert, 4),
        }

    out_path = os.path.join(RESULTS_DIR, "h_sensitivity.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved: {out_path}", flush=True)


if __name__ == "__main__":
    main()

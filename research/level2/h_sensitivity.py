"""Sensitivity analysis: sweep CUSUM threshold h = [2, 3, 4, 5, 6].

Re-runs CUSUMOnlyAgent with different h values on ALL strategy/market combos.
Uses cached IS results from results.json to avoid re-fetching data.

Usage: python research/level2/h_sensitivity.py
  (requires Binance data access — will re-fetch OHLCV)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev
from typing import Dict, List

from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import OHLCVSeries, Timeframe
from tradememory.simulation.agent import BaseAgent, SimulatedTrade
from tradememory.simulation.simulator import Simulator
from tradememory.simulation.strategy_generator import generate_strategy_grid

from cusum_agent import CUSUMOnlyAgent

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAMES = {"1h": Timeframe.H1, "4h": Timeframe.H4}
DAYS = 1095
IS_RATIO = 0.67
MAX_STRATEGIES = 50
MIN_IS_TRADES = 30
H_VALUES = [2.0, 3.0, 4.0, 5.0, 6.0]

RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))

import random
random.seed(42)


async def run_sensitivity():
    ds = BinanceDataSource()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=DAYS)

    all_strategies = generate_strategy_grid()
    print(f"Generated {len(all_strategies)} grid strategies")

    # For each h value, collect DD reduction vs BaseAgent
    h_results: Dict[float, List[float]] = {h: [] for h in H_VALUES}
    h_win_rates: Dict[float, List[int]] = {h: [] for h in H_VALUES}
    h_alert_rates: Dict[float, List[float]] = {h: [] for h in H_VALUES}

    for symbol in SYMBOLS:
        for tf_str, tf_enum in TIMEFRAMES.items():
            print(f"\n{'='*60}")
            print(f"{symbol} {tf_str}")
            print(f"{'='*60}")

            series = await ds.fetch_ohlcv(symbol, tf_enum, start, end)
            print(f"Got {len(series.bars)} bars")

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

            print(f"Qualified: {len(qualified)}")

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
                    cusum_dd = r_cusum.equity_max_dd

                    dd_reduction = base_dd - cusum_dd
                    h_results[h].append(dd_reduction)
                    h_win_rates[h].append(1 if dd_reduction > 0 else 0)

                    reduced = getattr(cusum, '_reduced_count', 0)
                    total = len(r_cusum.trades)
                    alert_rate = reduced / max(total, 1)
                    h_alert_rates[h].append(alert_rate)

                if (j + 1) % 10 == 0:
                    print(f"  [{j+1}/{len(qualified)}]", flush=True)

    # Print results
    print(f"\n{'='*70}")
    print("H SENSITIVITY ANALYSIS")
    print(f"{'='*70}")
    print(f"{'h':>5} | {'Win Rate':>10} | {'Mean DD Δ':>12} | {'Cohen d':>10} | {'p-value':>12} | {'Alert Rate':>12}")
    print("-" * 70)

    summary = {}
    for h in H_VALUES:
        diffs = h_results[h]
        n = len(diffs)
        m = mean(diffs)
        s = stdev(diffs) if n > 1 else 0.001
        wins = sum(h_win_rates[h])
        wr = wins / n
        d = m / s if s > 0 else 0
        t_stat, p_two = stats.ttest_1samp(diffs, 0)
        p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2
        avg_alert = mean(h_alert_rates[h])

        print(f"{h:5.1f} | {wr*100:9.1f}% | {m:+11.2f} | {d:9.4f} | {p_one:11.6f} | {avg_alert*100:10.1f}%")

        summary[str(h)] = {
            "n": n,
            "win_rate": round(wr, 4),
            "mean_dd_reduction": round(m, 2),
            "cohens_d": round(d, 4),
            "p_one_sided": round(p_one, 6),
            "avg_alert_rate": round(avg_alert, 4),
        }

    out_path = os.path.join(RESULTS_DIR, "h_sensitivity.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(run_sensitivity())

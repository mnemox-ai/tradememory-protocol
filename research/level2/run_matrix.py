"""Level 2: CUSUM Multi-Strategy Validation Matrix.

Tests CUSUM adaptive position sizing across 50+ strategies x 2 symbols x 2 timeframes.
Compares against BaseAgent + 3 naive baselines.

Usage:
  python research/level2/run_matrix.py                    # full matrix
  python research/level2/run_matrix.py --pilot             # pilot: 20 strategies, BTCUSDT 1h only
  python research/level2/run_matrix.py --max-strategies 30 # custom cap
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import OHLCVSeries, Timeframe
from tradememory.simulation.agent import BaseAgent, SimulatedTrade
from tradememory.simulation.simulator import Simulator, _compute_equity_metrics
from tradememory.simulation.strategy_generator import generate_strategy_grid

# Local imports
from cusum_agent import CUSUMOnlyAgent
from baselines_clean import PeriodicReduceAgent, RandomReduceAgent, SimpleWRAgent

# ── Config ──
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAMES = {"1h": Timeframe.H1, "4h": Timeframe.H4}
DAYS = 1095  # 3 years
IS_RATIO = 0.67
MAX_STRATEGIES = 50
MIN_IS_TRADES = 30

# Reproducibility
import random
random.seed(42)

RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))


def extract_metrics(result, agent) -> Dict:
    """Extract standardized metrics from a simulation result."""
    reduced = getattr(agent, '_reduced_count', 0)
    return {
        "trades": len(result.trades),
        "equity_pnl": result.equity_total_pnl,
        "equity_dd": result.equity_max_dd,
        "calmar": result.equity_calmar,
        "sharpe": result.fitness.sharpe_ratio,
        "win_rate": result.fitness.win_rate,
        "reduced_lot_trades": reduced,
    }


def run_agents_on_oos(
    strategy, is_result, oos_series, tf_str: str
) -> Dict[str, Dict]:
    """Run all 5 agents on OOS data for one strategy."""
    is_trades = is_result.trades

    # 1. BaseAgent (no calibration)
    base = BaseAgent(strategy, fixed_lot=0.01)
    r_base = Simulator(base, oos_series, tf_str).run()

    # 2. CUSUMOnlyAgent (warm-start + OOS)
    cusum = CUSUMOnlyAgent(strategy, fixed_lot=0.01, cusum_threshold=4.0)
    cusum.warm_start(is_trades)
    r_cusum = Simulator(cusum, oos_series, tf_str).run()

    # 3. PeriodicReduceAgent
    periodic = PeriodicReduceAgent(strategy, fixed_lot=0.01, period=50, reduce_pct=0.5, reduce_duration=10)
    periodic.warm_start(is_trades)
    r_periodic = Simulator(periodic, oos_series, tf_str).run()

    # 4. RandomReduceAgent
    rand_agent = RandomReduceAgent(strategy, fixed_lot=0.01, reduce_rate=0.3, reduce_pct=0.5, seed=42)
    rand_agent.warm_start(is_trades)
    r_random = Simulator(rand_agent, oos_series, tf_str).run()

    # 5. SimpleWRAgent (warm-start + OOS)
    swr = SimpleWRAgent(strategy, fixed_lot=0.01, window=20, threshold_delta=0.1, reduce_pct=0.5)
    swr.warm_start(is_trades)
    r_swr = Simulator(swr, oos_series, tf_str).run()

    return {
        "base": extract_metrics(r_base, base),
        "cusum": extract_metrics(r_cusum, cusum),
        "periodic": extract_metrics(r_periodic, periodic),
        "random": extract_metrics(r_random, rand_agent),
        "simple_wr": extract_metrics(r_swr, swr),
    }


async def run_matrix(pilot: bool = False, max_strategies: int = MAX_STRATEGIES):
    """Run the full experiment matrix."""
    ds = BinanceDataSource()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=DAYS)

    symbols = ["BTCUSDT"] if pilot else SYMBOLS
    timeframes = {"1h": Timeframe.H1} if pilot else TIMEFRAMES
    cap = min(20, max_strategies) if pilot else max_strategies

    all_strategies = generate_strategy_grid()
    print(f"Generated {len(all_strategies)} grid strategies")

    all_results = []
    total_combos = len(symbols) * len(timeframes)
    combo_idx = 0

    for symbol in symbols:
        for tf_str, tf_enum in timeframes.items():
            combo_idx += 1
            print(f"\n{'='*70}")
            print(f"[{combo_idx}/{total_combos}] {symbol} {tf_str}")
            print(f"{'='*70}")

            # Fetch data
            print(f"Fetching {symbol} {tf_str} ({DAYS} days)...")
            series = await ds.fetch_ohlcv(symbol, tf_enum, start, end)
            print(f"Got {len(series.bars)} bars")

            is_series, oos_series = series.split(IS_RATIO)
            print(f"IS: {len(is_series.bars)} bars, OOS: {len(oos_series.bars)} bars")

            # Filter strategies: need >= MIN_IS_TRADES in IS
            print(f"Qualifying strategies (IS trades >= {MIN_IS_TRADES})...", flush=True)
            qualified = []
            for i, strategy in enumerate(all_strategies):
                base_is = BaseAgent(strategy, fixed_lot=0.01)
                r_is = Simulator(base_is, is_series, tf_str).run()
                if r_is.fitness.trade_count >= MIN_IS_TRADES:
                    qualified.append((strategy, r_is))
                if (i + 1) % 20 == 0:
                    print(f"  checked {i+1}/{len(all_strategies)}, qualified {len(qualified)} so far", flush=True)
                if len(qualified) >= cap:
                    break

            print(f"Qualified: {len(qualified)}/{len(all_strategies)} (cap={cap})", flush=True)

            if not qualified:
                print("SKIP: No qualified strategies")
                continue

            # Run all agents on each qualified strategy
            t0 = time.time()
            combo_results = []
            for j, (strategy, is_result) in enumerate(qualified):
                print(f"  [{j+1}/{len(qualified)}] {strategy.name} "
                      f"(IS: {is_result.fitness.trade_count} trades, "
                      f"WR={is_result.fitness.win_rate:.2f})", end="")

                agent_results = run_agents_on_oos(strategy, is_result, oos_series, tf_str)

                # Quick summary
                base_dd = agent_results["base"]["equity_dd"]
                cusum_dd = agent_results["cusum"]["equity_dd"]
                dd_delta = base_dd - cusum_dd
                cusum_reduced = agent_results["cusum"]["reduced_lot_trades"]
                cusum_trades = agent_results["cusum"]["trades"]
                print(f" → DD: {base_dd:.0f}→{cusum_dd:.0f} "
                      f"(Δ{dd_delta:+.0f}), "
                      f"reduced={cusum_reduced}/{cusum_trades}", flush=True)

                record = {
                    "symbol": symbol,
                    "timeframe": tf_str,
                    "strategy_name": strategy.name,
                    "is_trades": is_result.fitness.trade_count,
                    "is_win_rate": round(is_result.fitness.win_rate, 4),
                    "agents": agent_results,
                }
                combo_results.append(record)

            elapsed = time.time() - t0
            print(f"\n{symbol} {tf_str}: {len(combo_results)} strategies in {elapsed:.1f}s")

            all_results.extend(combo_results)

            # Partial save
            partial_path = os.path.join(RESULTS_DIR, "results_partial.json")
            with open(partial_path, "w") as f:
                json.dump(all_results, f, indent=2)
            print(f"Partial save: {partial_path} ({len(all_results)} records)")

    # Final save
    final_path = os.path.join(RESULTS_DIR, "results.json")
    with open(final_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nFinal save: {final_path} ({len(all_results)} records)")

    return all_results


def print_summary(results: List[Dict]):
    """Quick summary table."""
    if not results:
        print("No results to summarize")
        return

    # Per-comparison DD differences
    comparisons = {
        "vs_base": [],
        "vs_periodic": [],
        "vs_random": [],
        "vs_simple_wr": [],
    }
    for r in results:
        a = r["agents"]
        cusum_dd = a["cusum"]["equity_dd"]
        comparisons["vs_base"].append(a["base"]["equity_dd"] - cusum_dd)
        comparisons["vs_periodic"].append(a["periodic"]["equity_dd"] - cusum_dd)
        comparisons["vs_random"].append(a["random"]["equity_dd"] - cusum_dd)
        comparisons["vs_simple_wr"].append(a["simple_wr"]["equity_dd"] - cusum_dd)

    print(f"\n{'='*70}")
    print(f"SUMMARY: {len(results)} strategies")
    print(f"{'='*70}")

    for name, diffs in comparisons.items():
        n = len(diffs)
        mean_d = sum(diffs) / n
        wins = sum(1 for d in diffs if d > 0)
        win_pct = wins / n * 100
        print(f"  {name}: mean DD Δ = {mean_d:+.2f}, CUSUM wins {wins}/{n} ({win_pct:.0f}%)")

    # Trade count sanity check
    base_trades = [r["agents"]["base"]["trades"] for r in results]
    cusum_trades = [r["agents"]["cusum"]["trades"] for r in results]
    mismatches = sum(1 for b, c in zip(base_trades, cusum_trades) if b != c)
    print(f"\n  Trade count mismatches (base vs cusum): {mismatches}/{len(results)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Level 2 CUSUM Matrix")
    parser.add_argument("--pilot", action="store_true", help="Pilot run: 20 strategies, BTCUSDT 1h only")
    parser.add_argument("--max-strategies", type=int, default=MAX_STRATEGIES, help="Max strategies per combo")
    args = parser.parse_args()

    results = asyncio.run(run_matrix(pilot=args.pilot, max_strategies=args.max_strategies))
    print_summary(results)

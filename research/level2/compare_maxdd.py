"""Compare CUSUM vs MaxDDStop baseline on existing Level 2 data.

Leverages results.json for base/cusum DD values (already computed).
Only runs MaxDDStopAgent on OOS data, then compares all three.

Usage: python research/level2/compare_maxdd.py
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
from tradememory.data.models import Timeframe
from tradememory.simulation.agent import BaseAgent
from tradememory.simulation.simulator import Simulator
from tradememory.simulation.strategy_generator import generate_strategy_grid

from cusum_agent import CUSUMOnlyAgent
from maxdd_baseline import MaxDDStopAgent

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAMES = {"1h": Timeframe.H1, "4h": Timeframe.H4}
DAYS = 1095
IS_RATIO = 0.67
MAX_STRATEGIES = 50
MIN_IS_TRADES = 30

RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))

import random
random.seed(42)


def load_cached_results() -> Dict[str, Dict]:
    """Load base/cusum DD from existing results.json.

    Returns dict keyed by 'SYMBOL_TF_STRATNAME' -> {base_dd, cusum_dd}.
    """
    results_path = os.path.join(RESULTS_DIR, "results.json")
    if not os.path.exists(results_path):
        return {}
    with open(results_path) as f:
        data = json.load(f)
    cache = {}
    for r in data:
        key = f"{r['symbol']}_{r['timeframe']}_{r['strategy_name']}"
        cache[key] = {
            "base_dd": r["agents"]["base"]["equity_dd"],
            "cusum_dd": r["agents"]["cusum"]["equity_dd"],
            "is_trades": r["is_trades"],
        }
    return cache


async def main():
    ds = BinanceDataSource()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=DAYS)

    all_strategies = generate_strategy_grid()
    strat_by_name = {s.name: s for s in all_strategies}
    print(f"Generated {len(all_strategies)} strategies")

    # Load cached base/cusum results
    cache = load_cached_results()
    print(f"Loaded {len(cache)} cached results from results.json")

    cusum_dds = []
    maxdd_dds = []
    base_dds = []

    for symbol in SYMBOLS:
        for tf_str, tf_enum in TIMEFRAMES.items():
            print(f"\n{'='*60}")
            print(f"{symbol} {tf_str}")
            print(f"{'='*60}")

            # Find cached strategies for this combo
            combo_prefix = f"{symbol}_{tf_str}_"
            cached_strats = {k: v for k, v in cache.items() if k.startswith(combo_prefix)}

            if not cached_strats:
                print(f"  No cached results for {symbol} {tf_str}, skipping")
                continue

            # Fetch data (needed for IS warm-start + OOS MaxDD run)
            print(f"  Fetching {symbol} {tf_str} ({DAYS} days)...")
            t0 = time.time()
            series = await ds.fetch_ohlcv(symbol, tf_enum, start, end)
            is_series, oos_series = series.split(IS_RATIO)
            print(f"  Got {len(series.bars)} bars ({time.time()-t0:.1f}s)")

            # Run IS qualification to get IS trades for warm-start
            # Only for strategies that are in the cache
            print(f"  Qualifying {len(cached_strats)} cached strategies for IS warm-start...")
            qualified = []
            checked = 0
            for key, cached in cached_strats.items():
                strat_name = key[len(combo_prefix):]
                strategy = strat_by_name.get(strat_name)
                if strategy is None:
                    continue

                base_is = BaseAgent(strategy, fixed_lot=0.01)
                r_is = Simulator(base_is, is_series, tf_str).run()
                qualified.append((strategy, r_is, cached))
                checked += 1
                if checked % 10 == 0:
                    print(f"    [{checked}/{len(cached_strats)}]", flush=True)

            print(f"  Qualified: {len(qualified)}")

            # Run MaxDDStop on each
            for j, (strategy, is_result, cached) in enumerate(qualified):
                is_trades = is_result.trades

                # MaxDDStop (15% threshold)
                maxdd = MaxDDStopAgent(strategy, fixed_lot=0.01, dd_threshold=0.15)
                maxdd.warm_start(is_trades)
                r_maxdd = Simulator(maxdd, oos_series, tf_str).run()

                base_dds.append(cached["base_dd"])
                cusum_dds.append(cached["cusum_dd"])
                maxdd_dds.append(r_maxdd.equity_max_dd)

                if (j + 1) % 10 == 0:
                    print(f"    [{j+1}/{len(qualified)}] maxdd_dd={r_maxdd.equity_max_dd:.0f}", flush=True)

            print(f"  Done: {len(qualified)} strategies")

    n = len(base_dds)
    print(f"\n{'='*70}")
    print(f"CUSUM vs MaxDDStop (N={n})")
    print(f"{'='*70}")

    # CUSUM vs Base
    diffs_cb = [b - c for b, c in zip(base_dds, cusum_dds)]
    m_cb = mean(diffs_cb)
    wins_cb = sum(1 for d in diffs_cb if d > 0)
    print(f"  CUSUM vs Base: wins={wins_cb}/{n} ({wins_cb/n*100:.1f}%), mean DD Δ={m_cb:+.2f}")

    # MaxDD vs Base
    diffs_mb = [b - m for b, m in zip(base_dds, maxdd_dds)]
    m_mb = mean(diffs_mb)
    wins_mb = sum(1 for d in diffs_mb if d > 0)
    print(f"  MaxDD vs Base: wins={wins_mb}/{n} ({wins_mb/n*100:.1f}%), mean DD Δ={m_mb:+.2f}")

    # CUSUM vs MaxDD (head-to-head)
    diffs_cm = [m - c for m, c in zip(maxdd_dds, cusum_dds)]
    m_cm = mean(diffs_cm)
    s_cm = stdev(diffs_cm) if n > 1 else 0.001
    wins_cm = sum(1 for d in diffs_cm if d > 0)
    d_cm = m_cm / s_cm if s_cm > 0 else 0
    t_cm, p2_cm = stats.ttest_1samp(diffs_cm, 0)
    p_cm = p2_cm / 2 if t_cm > 0 else 1 - p2_cm / 2

    print(f"\n  CUSUM vs MaxDDStop (head-to-head):")
    print(f"    CUSUM wins: {wins_cm}/{n} ({wins_cm/n*100:.1f}%)")
    print(f"    Mean DD Δ: {m_cm:+.2f}")
    print(f"    Cohen's d: {d_cm:.4f}")
    print(f"    p (one-sided): {p_cm:.6f}")

    output = {
        "n": n,
        "cusum_vs_base": {"win_rate": round(wins_cb/n, 4), "mean_dd_reduction": round(m_cb, 2)},
        "maxdd_vs_base": {"win_rate": round(wins_mb/n, 4), "mean_dd_reduction": round(m_mb, 2)},
        "cusum_vs_maxdd": {
            "win_rate": round(wins_cm/n, 4),
            "mean_dd_reduction": round(m_cm, 2),
            "cohens_d": round(d_cm, 4),
            "p_one_sided": round(p_cm, 6),
        },
    }
    out_path = os.path.join(RESULTS_DIR, "compare_maxdd.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

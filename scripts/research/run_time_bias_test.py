#!/usr/bin/env python3
"""Phase 13 Step 3: Time Bias Test.

Tests whether the specific entry hour matters, or if the trend filter alone
carries the edge. For each strategy (C and E), we run the original fixed-hour
version and then 24 variants (one per hour 0-23), keeping everything else identical.

If original >> mean of all hours → time-of-day matters.
If original ≈ mean → trend filter is the only alpha, hour is irrelevant.

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/run_time_bias_test.py
"""

import asyncio
import copy
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
# Add scripts/research dir for run_real_baseline
sys.path.insert(0, str(Path(__file__).parent))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.context_builder import ContextConfig
from tradememory.data.models import Timeframe
from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    RuleCondition,
)

# Reuse from Step 1
from run_real_baseline import (
    build_strategy_c,
    build_strategy_e,
    fast_backtest,
    precompute_atrs,
    precompute_contexts,
)


def make_hour_variant(pattern: CandidatePattern, new_hour: int) -> CandidatePattern:
    """Deep copy a pattern and change the hour_utc condition to new_hour."""
    variant = pattern.model_copy(deep=True)
    for cond in variant.entry_condition.conditions:
        if cond.field == "hour_utc":
            cond.value = new_hour
            break
    variant.pattern_id = f"{pattern.pattern_id}-H{new_hour:02d}"
    variant.name = f"{pattern.name} (hour={new_hour})"
    return variant


def compute_percentile(value: float, distribution: List[float]) -> float:
    """Compute percentile rank of value within a sorted distribution."""
    if not distribution:
        return 0.0
    count_below = sum(1 for v in distribution if v < value)
    return round(100.0 * count_below / len(distribution), 1)


async def main():
    print("=" * 70)
    print("Phase 13 Step 3: Time Bias Test")
    print("=" * 70)
    print("Question: Does the specific entry HOUR matter,")
    print("or does the trend filter alone carry the edge?")

    # --- Step 1: Fetch data ---
    print("\n[1/4] Fetching BTCUSDT 1H data from Binance...")
    start_dt = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 3, 17, tzinfo=timezone.utc)

    binance = BinanceDataSource()
    try:
        series = await binance.fetch_ohlcv(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            start=start_dt,
            end=end_dt,
        )
    finally:
        await binance.close()

    bars = series.bars
    print(f"  Bars: {series.count}")
    print(f"  Period: {series.start} -> {series.end}")

    # --- Step 2: Precompute contexts + ATR ---
    print("\n[2/4] Precomputing MarketContext + ATR...")
    t0 = time.time()
    contexts = precompute_contexts(series)
    atrs = precompute_atrs(bars)
    precompute_time = time.time() - t0
    print(f"  Done in {precompute_time:.1f}s")

    # --- Step 3: Run time bias test for each strategy ---
    print("\n[3/4] Running time bias test...")

    strategies = {
        "C": {"builder": build_strategy_c, "original_hour": 16},
        "E": {"builder": build_strategy_e, "original_hour": 14},
    }

    results = {}

    for strat_name, info in strategies.items():
        print(f"\n  --- Strategy {strat_name} (original hour={info['original_hour']}) ---")
        original = info["builder"]()

        # Backtest original
        orig_metrics = fast_backtest(bars, contexts, atrs, original, timeframe="1h")
        orig_sharpe = orig_metrics.sharpe_ratio
        orig_trades = orig_metrics.trade_count
        orig_wr = orig_metrics.win_rate
        print(f"  Original (H{info['original_hour']:02d}): "
              f"Sharpe={orig_sharpe:.4f}, trades={orig_trades}, WR={orig_wr:.1%}")

        # Run all 24 hour variants
        hour_sharpes = {}
        hour_trades = {}
        hour_wrs = {}
        for h in range(24):
            variant = make_hour_variant(original, h)
            metrics = fast_backtest(bars, contexts, atrs, variant, timeframe="1h")
            hour_sharpes[h] = metrics.sharpe_ratio
            hour_trades[h] = metrics.trade_count
            hour_wrs[h] = metrics.win_rate

        # Stats
        all_sharpes = sorted(hour_sharpes.values())
        mean_sharpe = sum(all_sharpes) / len(all_sharpes)
        std_sharpe = math.sqrt(sum((s - mean_sharpe) ** 2 for s in all_sharpes) / (len(all_sharpes) - 1))
        median_sharpe = all_sharpes[12]  # 24 values, median = average of 12th and 13th
        best_hour = max(hour_sharpes, key=hour_sharpes.get)
        worst_hour = min(hour_sharpes, key=hour_sharpes.get)

        # Percentile of original within the 24-hour distribution
        orig_pctile = compute_percentile(orig_sharpe, all_sharpes)

        # How many hours have positive Sharpe?
        positive_hours = sum(1 for s in all_sharpes if s > 0)

        print(f"\n  24-hour distribution:")
        print(f"    Mean Sharpe:   {mean_sharpe:.4f}")
        print(f"    Std Sharpe:    {std_sharpe:.4f}")
        print(f"    Median Sharpe: {median_sharpe:.4f}")
        print(f"    Best hour:     H{best_hour:02d} (Sharpe={hour_sharpes[best_hour]:.4f})")
        print(f"    Worst hour:    H{worst_hour:02d} (Sharpe={hour_sharpes[worst_hour]:.4f})")
        print(f"    Positive hours: {positive_hours}/24")
        print(f"    Original percentile vs 24h: P{orig_pctile:.0f}")

        # Print all hours
        print(f"\n  Hour | Sharpe  | Trades | WR     | vs Original")
        print(f"  -----|---------|--------|--------|------------")
        for h in range(24):
            marker = " <<<" if h == info["original_hour"] else ""
            delta = hour_sharpes[h] - orig_sharpe
            print(f"  H{h:02d}  | {hour_sharpes[h]:>7.4f} | {hour_trades[h]:>6d} | {hour_wrs[h]:>5.1%} | {delta:>+7.4f}{marker}")

        results[strat_name] = {
            "original_hour": info["original_hour"],
            "original_sharpe": orig_sharpe,
            "original_trades": orig_trades,
            "original_win_rate": orig_wr,
            "mean_sharpe_all_hours": round(mean_sharpe, 4),
            "std_sharpe_all_hours": round(std_sharpe, 4),
            "median_sharpe": round(median_sharpe, 4),
            "best_hour": best_hour,
            "best_sharpe": round(hour_sharpes[best_hour], 4),
            "worst_hour": worst_hour,
            "worst_sharpe": round(hour_sharpes[worst_hour], 4),
            "positive_hours": positive_hours,
            "original_percentile_vs_24h": orig_pctile,
            "hourly_sharpes": {str(h): round(s, 4) for h, s in hour_sharpes.items()},
            "hourly_trades": {str(h): t for h, t in hour_trades.items()},
            "hourly_win_rates": {str(h): round(w, 4) for h, w in hour_wrs.items()},
        }

    # --- Step 4: Verdict ---
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    for strat_name, r in results.items():
        orig = r["original_sharpe"]
        mean = r["mean_sharpe_all_hours"]
        std = r["std_sharpe_all_hours"]
        pctile = r["original_percentile_vs_24h"]
        best_h = r["best_hour"]
        best_s = r["best_sharpe"]

        print(f"\nStrategy {strat_name}:")
        print(f"  Original hour H{r['original_hour']:02d}: Sharpe = {orig:.4f}")
        print(f"  Mean across all 24 hours:       Sharpe = {mean:.4f}")
        print(f"  Std across all 24 hours:                  {std:.4f}")
        print(f"  Original percentile:            P{pctile:.0f}")
        print(f"  Best hour: H{best_h:02d} (Sharpe={best_s:.4f})")

        # Interpretation
        if mean > 0 and orig > 0:
            ratio = orig / mean if mean != 0 else float('inf')
            print(f"  Original/Mean ratio:            {ratio:.2f}x")

        if std > 0:
            z_score = (orig - mean) / std
            print(f"  Z-score vs hour distribution:   {z_score:.2f}")
        else:
            z_score = 0

        # Decision
        if pctile >= 80 and z_score >= 1.0:
            print(f"  --> HOUR MATTERS: Original hour is significantly above average.")
            print(f"      The specific entry time adds alpha beyond the trend filter.")
        elif pctile >= 60:
            print(f"  --> HOUR HAS MILD EFFECT: Original is above average but not dominant.")
            print(f"      Trend filter does most of the work, hour provides slight edge.")
        else:
            print(f"  --> HOUR DOES NOT MATTER: Original hour is near or below average.")
            print(f"      The trend filter alone carries the edge; hour is noise.")

    # Overall
    print("\n" + "-" * 70)
    c_res = results["C"]
    e_res = results["E"]
    c_positive = c_res["positive_hours"]
    e_positive = e_res["positive_hours"]
    print(f"\nTrend filter strength indicator:")
    print(f"  Strategy C: {c_positive}/24 hours profitable with trend filter")
    print(f"  Strategy E: {e_positive}/24 hours profitable with trend filter")
    print(f"  (If most hours are profitable, the trend filter is the main alpha)")

    # Save results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test": "Phase 13 Step 3: Time Bias Test",
        "data_period": f"{start_dt.date()} to {end_dt.date()}",
        "bars": series.count,
        "method": "Run original strategy + 24 hour variants (0-23), compare Sharpe distributions",
        "strategies": results,
    }
    out_path = Path(__file__).parent.parent / "validation_step3_results.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

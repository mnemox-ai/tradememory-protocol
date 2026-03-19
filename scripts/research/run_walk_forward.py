#!/usr/bin/env python3
"""Phase 13 Step 2: Walk-Forward Validation.

Rolling windows: 3 months train, 1 month test, slide by 1 month.
Tests OOS stability of Strategy C and E on BTCUSDT 1H data.

Pass criteria:
  - OOS Sharpe > 0 in >= 60% of windows
  - Mean OOS Sharpe > 1.0
  - No single window with OOS max drawdown > 50%

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/run_walk_forward.py
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
# Also add scripts/research dir so we can import from run_real_baseline
sys.path.insert(0, str(Path(__file__).parent))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.context_builder import ContextConfig
from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.models import CandidatePattern, FitnessMetrics

from run_real_baseline import (
    build_strategy_c,
    build_strategy_e,
    fast_backtest,
    precompute_atrs,
    precompute_contexts,
)


def month_boundaries(start_year: int, start_month: int, n_months: int) -> List[datetime]:
    """Generate monthly boundary datetimes in UTC.

    Returns n_months + 1 boundaries (start of each month).
    E.g. month_boundaries(2024, 6, 3) -> [2024-06-01, 2024-07-01, 2024-08-01, 2024-09-01]
    """
    boundaries = []
    year, month = start_year, start_month
    for _ in range(n_months + 1):
        boundaries.append(datetime(year, month, 1, tzinfo=timezone.utc))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return boundaries


def slice_bars_by_date(
    bars: List[OHLCV], start: datetime, end: datetime
) -> Tuple[List[OHLCV], int, int]:
    """Return bars where start <= bar.timestamp < end.

    Also returns the start and end indices in the original bars list.
    """
    start_idx = None
    end_idx = None
    for i, bar in enumerate(bars):
        if bar.timestamp >= start and start_idx is None:
            start_idx = i
        if bar.timestamp >= end:
            end_idx = i
            break
    if start_idx is None:
        return [], 0, 0
    if end_idx is None:
        end_idx = len(bars)
    return bars[start_idx:end_idx], start_idx, end_idx


def backtest_window(
    bars: List[OHLCV],
    contexts: list,
    atrs: list,
    pattern: CandidatePattern,
    start_idx: int,
    end_idx: int,
    timeframe: str = "1h",
) -> FitnessMetrics:
    """Backtest a pattern on a sub-window of bars using precomputed contexts/atrs.

    Slices bars, contexts, atrs to [start_idx:end_idx] and runs fast_backtest.
    """
    window_bars = bars[start_idx:end_idx]
    window_contexts = contexts[start_idx:end_idx]
    window_atrs = atrs[start_idx:end_idx]
    return fast_backtest(window_bars, window_contexts, window_atrs, pattern, timeframe=timeframe)


async def main():
    print("=" * 70)
    print("Phase 13 Step 2: Walk-Forward Validation")
    print("=" * 70)

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

    # --- Step 2: Precompute contexts + ATR for full dataset ---
    print("\n[2/4] Precomputing MarketContext + ATR for all bars...")
    t0 = time.time()
    contexts = precompute_contexts(series)
    atrs = precompute_atrs(bars)
    precompute_time = time.time() - t0
    valid_ctx = sum(1 for c in contexts if c is not None)
    print(f"  Done in {precompute_time:.1f}s ({valid_ctx} valid contexts)")

    # --- Step 3: Walk-forward windows ---
    print("\n[3/4] Running walk-forward windows...")
    # Data spans Jun 2024 - Mar 2026 = 21 months
    # Train: 3 months, Test: 1 month, slide by 1 month
    # Window 1: train Jun-Aug 2024, test Sep 2024
    # Window 2: train Jul-Sep 2024, test Oct 2024
    # ...last window depends on data availability

    # Generate monthly boundaries from Jun 2024 to Mar 2026
    all_boundaries = month_boundaries(2024, 6, 21)  # Jun 2024 through Mar 2026

    strategies = {
        "Strategy C": build_strategy_c(),
        "Strategy E": build_strategy_e(),
    }

    train_months = 3
    test_months = 1
    min_window_months = train_months + test_months  # 4

    # Build windows: each window needs train_months + test_months consecutive months
    windows = []
    for i in range(len(all_boundaries) - min_window_months):
        train_start = all_boundaries[i]
        train_end = all_boundaries[i + train_months]
        test_start = train_end
        test_end = all_boundaries[i + min_window_months]
        windows.append({
            "id": i + 1,
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
        })

    print(f"  Total windows: {len(windows)}")
    print(f"  Train: {train_months} months, Test: {test_months} month")

    # Run backtest for each window and strategy
    results_by_strategy: Dict[str, List[dict]] = {name: [] for name in strategies}

    for w in windows:
        # Get bar index ranges for train and test
        _, train_start_idx, train_end_idx = slice_bars_by_date(
            bars, w["train_start"], w["train_end"]
        )
        _, test_start_idx, test_end_idx = slice_bars_by_date(
            bars, w["test_start"], w["test_end"]
        )

        train_label = f"{w['train_start'].strftime('%Y-%m')} to {w['train_end'].strftime('%Y-%m')}"
        test_label = f"{w['test_start'].strftime('%Y-%m')}"

        for name, pattern in strategies.items():
            # In-sample (train)
            is_metrics = backtest_window(
                bars, contexts, atrs, pattern, train_start_idx, train_end_idx
            )
            # Out-of-sample (test)
            oos_metrics = backtest_window(
                bars, contexts, atrs, pattern, test_start_idx, test_end_idx
            )

            window_result = {
                "window_id": w["id"],
                "train_period": train_label,
                "test_period": test_label,
                "is_sharpe": is_metrics.sharpe_ratio,
                "is_trades": is_metrics.trade_count,
                "is_win_rate": is_metrics.win_rate,
                "is_pnl": is_metrics.total_pnl,
                "oos_sharpe": oos_metrics.sharpe_ratio,
                "oos_trades": oos_metrics.trade_count,
                "oos_win_rate": oos_metrics.win_rate,
                "oos_pnl": oos_metrics.total_pnl,
                "oos_max_dd": oos_metrics.max_drawdown_pct,
            }
            results_by_strategy[name].append(window_result)

        # Progress indicator
        if w["id"] % 5 == 0 or w["id"] == len(windows):
            print(f"    Window {w['id']}/{len(windows)} done")

    # --- Step 4: Evaluate pass criteria ---
    print("\n[4/4] Evaluating pass criteria...")
    print()

    strategy_summaries = {}

    for name in strategies:
        window_results = results_by_strategy[name]
        n_windows = len(window_results)

        oos_sharpes = [r["oos_sharpe"] for r in window_results]
        oos_max_dds = [r["oos_max_dd"] for r in window_results]
        oos_trades = [r["oos_trades"] for r in window_results]

        # Criteria
        n_positive = sum(1 for s in oos_sharpes if s > 0)
        pct_positive = n_positive / n_windows if n_windows > 0 else 0
        mean_oos_sharpe = sum(oos_sharpes) / n_windows if n_windows > 0 else 0
        worst_dd = max(oos_max_dds) if oos_max_dds else 0  # max_drawdown_pct is already positive
        total_oos_trades = sum(oos_trades)

        pass_positive = pct_positive >= 0.60
        pass_mean_sharpe = mean_oos_sharpe > 1.0
        pass_max_dd = worst_dd <= 50.0
        overall_pass = pass_positive and pass_mean_sharpe and pass_max_dd

        summary = {
            "n_windows": n_windows,
            "oos_sharpes": [round(s, 4) for s in oos_sharpes],
            "n_positive_sharpe": n_positive,
            "pct_positive_sharpe": round(pct_positive * 100, 1),
            "mean_oos_sharpe": round(mean_oos_sharpe, 4),
            "median_oos_sharpe": round(sorted(oos_sharpes)[n_windows // 2], 4) if n_windows > 0 else 0,
            "min_oos_sharpe": round(min(oos_sharpes), 4) if oos_sharpes else 0,
            "max_oos_sharpe": round(max(oos_sharpes), 4) if oos_sharpes else 0,
            "worst_oos_dd": round(worst_dd, 2),
            "total_oos_trades": total_oos_trades,
            "pass_positive_60pct": pass_positive,
            "pass_mean_sharpe_gt1": pass_mean_sharpe,
            "pass_max_dd_lt50": pass_max_dd,
            "overall_pass": overall_pass,
        }
        strategy_summaries[name] = summary

        # Print per-window details
        print(f"{'=' * 70}")
        print(f"  {name}")
        print(f"{'=' * 70}")
        print(f"  {'Window':<8} {'Test Period':<12} {'IS Sharpe':>10} {'OOS Sharpe':>11} "
              f"{'OOS Trades':>11} {'OOS WR':>8} {'OOS DD%':>8}")
        print(f"  {'-' * 68}")
        for r in window_results:
            print(f"  {r['window_id']:<8} {r['test_period']:<12} "
                  f"{r['is_sharpe']:>10.4f} {r['oos_sharpe']:>11.4f} "
                  f"{r['oos_trades']:>11d} {r['oos_win_rate']:>7.1%} "
                  f"{r['oos_max_dd']:>7.1f}%")

        print()
        print(f"  Summary:")
        print(f"    OOS Sharpe > 0:  {n_positive}/{n_windows} = {pct_positive:.1%} "
              f"(need >= 60%) {'PASS' if pass_positive else 'FAIL'}")
        print(f"    Mean OOS Sharpe: {mean_oos_sharpe:.4f} "
              f"(need > 1.0) {'PASS' if pass_mean_sharpe else 'FAIL'}")
        print(f"    Worst OOS DD:    {worst_dd:.1f}% "
              f"(need <= 50%) {'PASS' if pass_max_dd else 'FAIL'}")
        print(f"    Overall:         {'PASS' if overall_pass else 'FAIL'}")
        print()

    # --- Final Verdict ---
    print("=" * 70)
    print("WALK-FORWARD VERDICT")
    print("=" * 70)

    all_pass = all(s["overall_pass"] for s in strategy_summaries.values())
    any_pass = any(s["overall_pass"] for s in strategy_summaries.values())

    print(f"\n{'Strategy':<20} {'Windows':>8} {'OOS>0 %':>10} {'Mean OOS':>10} "
          f"{'Worst DD':>10} {'Result':>8}")
    print("-" * 70)
    for name, s in strategy_summaries.items():
        result = "PASS" if s["overall_pass"] else "FAIL"
        print(f"{name:<20} {s['n_windows']:>8} {s['pct_positive_sharpe']:>9.1f}% "
              f"{s['mean_oos_sharpe']:>10.4f} {s['worst_oos_dd']:>9.1f}% {result:>8}")

    print()
    if all_pass:
        print("Both strategies pass walk-forward validation.")
        print("-> Proceed to Step 3 (Live Paper Trading)")
    elif any_pass:
        passed = [n for n, s in strategy_summaries.items() if s["overall_pass"]]
        failed = [n for n, s in strategy_summaries.items() if not s["overall_pass"]]
        print(f"PASS: {', '.join(passed)}")
        print(f"FAIL: {', '.join(failed)}")
        print("-> Investigate failing strategy, consider parameter tuning or dropping")
    else:
        print("Both strategies fail walk-forward validation.")
        print("-> Strategies may be overfit. Revisit signal logic.")

    # --- Save results ---
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_period": f"{start_dt.date()} to {end_dt.date()}",
        "bars": series.count,
        "train_months": train_months,
        "test_months": test_months,
        "n_windows": len(windows),
        "strategies": {},
    }
    for name in strategies:
        output["strategies"][name] = {
            "summary": strategy_summaries[name],
            "windows": results_by_strategy[name],
        }

    out_path = Path(__file__).parent.parent / "validation_step2_results.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

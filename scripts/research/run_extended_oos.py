#!/usr/bin/env python3
"""Phase 13 Step 4: Extended Out-of-Sample Validation.

Fetches BTCUSDT 1H data from January 2020 to June 2024 (~39,000 bars),
runs Strategy C and E, plus 1000 random baseline, and compares with
the original Jun 2024 - Mar 2026 period results.

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/run_extended_oos.py
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add scripts/research dir and project root to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_real_baseline import (
    build_strategy_c,
    build_strategy_e,
    fast_backtest,
    fast_run_baseline,
    precompute_atrs,
    precompute_contexts,
)

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import Timeframe
from tradememory.evolution.random_baseline import compute_percentile_rank


# Original period results (from Step 1) for comparison
ORIGINAL_RESULTS = {
    "period": "2024-06-01 to 2026-03-17",
    "bars": 15288,
    "Strategy C": {"sharpe": 3.3952, "percentile": 96.9, "trades": 130, "win_rate": 0.438, "pf": 2.10},
    "Strategy E": {"sharpe": 4.4175, "percentile": 100.0, "trades": 161, "win_rate": 0.460, "pf": 2.62},
}


async def main():
    print("=" * 70)
    print("Phase 13 Step 4: Extended OOS Validation (2020-2024)")
    print("=" * 70)

    # --- Step 1: Fetch extended historical data ---
    print("\n[1/5] Fetching BTCUSDT 1H data from Binance (2020-01 to 2024-06)...")
    start_dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(2024, 6, 1, tzinfo=timezone.utc)

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
    print(f"  First close: ${bars[0].close:,.0f}")
    print(f"  Last close: ${bars[-1].close:,.0f}")

    # --- Step 2: Precompute contexts + ATR ---
    print("\n[2/5] Precomputing MarketContext + ATR for all bars...")
    t0 = time.time()
    contexts = precompute_contexts(series)
    atrs = precompute_atrs(bars)
    precompute_time = time.time() - t0
    valid_ctx = sum(1 for c in contexts if c is not None)
    print(f"  Done in {precompute_time:.1f}s ({valid_ctx} valid contexts)")

    # --- Step 3: Backtest Strategy C and E ---
    print("\n[3/5] Backtesting Strategy C and E...")
    strat_c = build_strategy_c()
    strat_e = build_strategy_e()

    metrics_c = fast_backtest(bars, contexts, atrs, strat_c, timeframe="1h")
    metrics_e = fast_backtest(bars, contexts, atrs, strat_e, timeframe="1h")

    strategy_results = {
        "Strategy C": {
            "sharpe": metrics_c.sharpe_ratio,
            "trades": metrics_c.trade_count,
            "win_rate": metrics_c.win_rate,
            "pf": metrics_c.profit_factor,
            "total_pnl": metrics_c.total_pnl,
            "max_dd": metrics_c.max_drawdown_pct,
            "avg_hold": metrics_c.avg_holding_bars,
        },
        "Strategy E": {
            "sharpe": metrics_e.sharpe_ratio,
            "trades": metrics_e.trade_count,
            "win_rate": metrics_e.win_rate,
            "pf": metrics_e.profit_factor,
            "total_pnl": metrics_e.total_pnl,
            "max_dd": metrics_e.max_drawdown_pct,
            "avg_hold": metrics_e.avg_holding_bars,
        },
    }

    for name, r in strategy_results.items():
        print(f"  {name}: Sharpe={r['sharpe']:.4f}, trades={r['trades']}, "
              f"WR={r['win_rate']:.1%}, PF={r['pf']:.2f}, PnL=${r['total_pnl']:.2f}")

    # --- Step 4: Run 1000 random baseline ---
    print("\n[4/5] Running 1000 random strategies (this may take a while)...")
    t1 = time.time()
    baseline = fast_run_baseline(bars, contexts, atrs, n_strategies=1000, seed=42, timeframe="1h")
    baseline_time = time.time() - t1
    print(f"  Done in {baseline_time:.1f}s")
    print(f"  Mean Sharpe: {baseline.mean_sharpe:.4f}")
    print(f"  Std Sharpe:  {baseline.std_sharpe:.4f}")

    dist = baseline.sharpe_distribution
    p5 = dist[int(len(dist) * 0.05)] if dist else 0
    p25 = dist[int(len(dist) * 0.25)] if dist else 0
    p50 = dist[int(len(dist) * 0.50)] if dist else 0
    p75 = dist[int(len(dist) * 0.75)] if dist else 0
    p95 = baseline.percentile_95

    print(f"\n  Distribution:")
    print(f"    P5:  {p5:.4f}")
    print(f"    P25: {p25:.4f}")
    print(f"    P50: {p50:.4f}")
    print(f"    P75: {p75:.4f}")
    print(f"    P95: {p95:.4f}")
    print(f"    Min: {dist[0]:.4f}" if dist else "    Min: N/A")
    print(f"    Max: {dist[-1]:.4f}" if dist else "    Max: N/A")

    # --- Step 5: Rank and compare ---
    print("\n[5/5] Ranking against random baseline...")

    pctile_c = compute_percentile_rank(strategy_results["Strategy C"]["sharpe"], baseline.sharpe_distribution)
    pctile_e = compute_percentile_rank(strategy_results["Strategy E"]["sharpe"], baseline.sharpe_distribution)

    c_passes = pctile_c >= 95.0
    e_passes = pctile_e >= 95.0

    strategy_results["Strategy C"]["percentile"] = pctile_c
    strategy_results["Strategy C"]["passes_95pct"] = c_passes
    strategy_results["Strategy E"]["percentile"] = pctile_e
    strategy_results["Strategy E"]["passes_95pct"] = e_passes

    # --- Print results ---
    print("\n" + "=" * 70)
    print("EXTENDED OOS RESULTS (2020-01 to 2024-06)")
    print("=" * 70)
    print(f"\nData: BTCUSDT 1H, {series.count} bars")
    print(f"Period: {start_dt.date()} -> {end_dt.date()}")
    print(f"Baseline: 1000 random strategies, mean={baseline.mean_sharpe:.4f}, "
          f"std={baseline.std_sharpe:.4f}, P95={p95:.4f}")
    print(f"Timing: precompute={precompute_time:.0f}s, "
          f"baseline={baseline_time:.0f}s, total={precompute_time + baseline_time:.0f}s")

    print(f"\n{'Strategy':<20} {'Sharpe':>8} {'Pctile':>8} {'Trades':>8} "
          f"{'WR':>8} {'PF':>8} {'PnL':>12} {'Pass?':>8}")
    print("-" * 80)
    for name in ["Strategy C", "Strategy E"]:
        r = strategy_results[name]
        status = "PASS" if r["passes_95pct"] else "FAIL"
        print(f"{name:<20} {r['sharpe']:>8.4f} {r['percentile']:>7.1f}% "
              f"{r['trades']:>8d} {r['win_rate']:>7.1%} {r['pf']:>8.2f} "
              f"${r['total_pnl']:>10.2f} {status:>8}")

    # --- Comparison with original period ---
    print("\n" + "=" * 70)
    print("COMPARISON: Extended OOS vs Original Period")
    print("=" * 70)
    print(f"\n{'Metric':<20} {'Extended OOS (2020-2024)':<30} {'Original (2024-2026)':<30}")
    print("-" * 80)

    orig = ORIGINAL_RESULTS
    for strat in ["Strategy C", "Strategy E"]:
        print(f"\n  {strat}:")
        ext = strategy_results[strat]
        ori = orig[strat]
        print(f"    {'Sharpe':<16} {ext['sharpe']:>10.4f}              {ori['sharpe']:>10.4f}")
        print(f"    {'Percentile':<16} {ext['percentile']:>9.1f}%              {ori['percentile']:>9.1f}%")
        print(f"    {'Trades':<16} {ext['trades']:>10d}              {ori['trades']:>10d}")
        print(f"    {'Win Rate':<16} {ext['win_rate']:>9.1%}              {ori['win_rate']:>9.1%}")
        print(f"    {'Profit Factor':<16} {ext['pf']:>10.2f}              {ori['pf']:>10.2f}")

    # --- Verdict ---
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    if c_passes and e_passes:
        print("BOTH strategies pass extended OOS validation.")
        print("Strong evidence of real edge across different market regimes.")
    elif e_passes and not c_passes:
        print("Strategy E PASSES extended OOS — robust edge confirmed.")
        print("Strategy C FAILS extended OOS — edge may be regime-dependent.")
    elif c_passes and not e_passes:
        print("Strategy C PASSES extended OOS — robust edge confirmed.")
        print("Strategy E FAILS extended OOS — edge may be regime-dependent.")
    else:
        print("NEITHER strategy passes extended OOS validation.")
        print("Edges found in 2024-2026 may be overfitted to that specific regime.")

    # Additional context
    print(f"\nNote: BTC 2020-2024 includes:")
    print(f"  - COVID crash (Mar 2020)")
    print(f"  - Bull run to $69K (Nov 2021)")
    print(f"  - Bear market to $16K (Nov 2022)")
    print(f"  - Recovery to $73K (Mar 2024)")
    print(f"  This is a much more diverse market regime test.")

    # --- Save results ---
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step": "Phase 13 Step 4: Extended OOS Validation",
        "extended_oos": {
            "period": f"{start_dt.date()} to {end_dt.date()}",
            "bars": series.count,
            "n_random": 1000,
            "seed": 42,
            "baseline": {
                "mean_sharpe": baseline.mean_sharpe,
                "std_sharpe": baseline.std_sharpe,
                "p5": round(p5, 4),
                "p25": round(p25, 4),
                "p50": round(p50, 4),
                "p75": round(p75, 4),
                "p95": round(p95, 4),
            },
            "strategies": {
                name: {k: v for k, v in r.items()}
                for name, r in strategy_results.items()
            },
        },
        "original_period": ORIGINAL_RESULTS,
        "verdict": {
            "strategy_c_passes": c_passes,
            "strategy_e_passes": e_passes,
        },
    }
    out_path = Path(__file__).parent.parent / "validation_step4_results.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

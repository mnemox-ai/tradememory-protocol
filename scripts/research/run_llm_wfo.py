#!/usr/bin/env python3
"""Phase 15 Exp 4b: LLM Walk-Forward Optimization (WFO).

Mirrors Exp 4a (Grid WFO) design but replaces grid search with EvolutionEngine.

Four arms:
  Arm L  — LLM WFO with DSR gate
  Arm G  — Grid WFO + DSR gate (from Exp 4a, read from file)
  Ctrl A — Static Strategy E (from Exp 4a)
  Ctrl B — Buy & Hold (from Exp 4a)

Pilot mode: runs first 5 periods, computes Cohen's d, then stops for review.

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    set ANTHROPIC_API_KEY=sk-ant-...
    python scripts/research/run_llm_wfo.py [--full]
"""

import argparse
import asyncio
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.engine import EngineConfig
from tradememory.evolution.llm import AnthropicClient
from tradememory.evolution.models import EvolutionConfig
from tradememory.evolution.re_evolution import LLMReEvolutionPipeline
from tradememory.evolution.strategy_registry import StrategyRegistry

from run_real_baseline import fast_backtest, precompute_atrs, precompute_contexts
from run_walk_forward import month_boundaries, slice_bars_by_date
from strategy_definitions import build_strategy_e
from run_grid_wfo import compute_buy_and_hold_sharpe


def cohens_d(group_a: List[float], group_b: List[float]) -> float:
    """Compute Cohen's d between two groups."""
    if len(group_a) < 2 or len(group_b) < 2:
        return 0.0
    mean_a = sum(group_a) / len(group_a)
    mean_b = sum(group_b) / len(group_b)
    var_a = sum((x - mean_a) ** 2 for x in group_a) / (len(group_a) - 1)
    var_b = sum((x - mean_b) ** 2 for x in group_b) / (len(group_b) - 1)
    pooled_var = ((len(group_a) - 1) * var_a + (len(group_b) - 1) * var_b) / (
        len(group_a) + len(group_b) - 2
    )
    pooled_std = math.sqrt(pooled_var) if pooled_var > 0 else 1e-10
    return (mean_a - mean_b) / pooled_std


def wilcoxon_approx(x: List[float], y: List[float]) -> float:
    """Approximate Wilcoxon signed-rank test p-value using normal approximation.

    Returns approximate two-sided p-value. For exact test, use scipy.
    """
    diffs = [a - b for a, b in zip(x, y) if a != b]
    if not diffs:
        return 1.0
    n = len(diffs)
    abs_diffs = [(abs(d), i) for i, d in enumerate(diffs)]
    abs_diffs.sort()
    ranks = list(range(1, n + 1))
    # Handle ties: average ranks
    w_plus = sum(r for r, (_, i) in zip(ranks, abs_diffs) if diffs[i] > 0)
    mean_w = n * (n + 1) / 4
    std_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if std_w == 0:
        return 1.0
    z = (w_plus - mean_w) / std_w
    # Two-sided p-value from normal approximation
    p = 2 * (1 - _norm_cdf(abs(z)))
    return p


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Run all 23 periods (not just pilot)")
    args = parser.parse_args()

    pilot_periods = 5
    max_periods = None if args.full else pilot_periods

    print("=" * 70)
    print(f"Phase 15 Exp 4b: LLM WFO {'(FULL)' if args.full else f'(PILOT — {pilot_periods} periods)'}")
    print("=" * 70)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    # --- Load Exp 4a results (Grid, Controls) ---
    exp4a_path = Path(__file__).parent.parent.parent / "validation" / "grid_wfo_results.json"
    if not exp4a_path.exists():
        print(f"ERROR: Exp 4a results not found at {exp4a_path}")
        print("Run scripts/research/run_grid_wfo.py first.")
        sys.exit(1)

    exp4a = json.loads(exp4a_path.read_text(encoding="utf-8"))
    exp4a_arms = exp4a["arms"]
    exp4a_n = len(exp4a_arms["arm_g"])
    print(f"  Loaded Exp 4a: {exp4a_n} periods")

    # --- Fetch data ---
    data_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    data_end = datetime(2026, 3, 1, tzinfo=timezone.utc)
    is_months = 3
    oos_months = 3

    print(f"\n[1/4] Fetching BTCUSDT 1H data ({data_start.date()} to {data_end.date()})...")
    binance = BinanceDataSource()
    try:
        series = await binance.fetch_ohlcv(
            symbol="BTCUSDT", timeframe=Timeframe.H1,
            start=data_start, end=data_end,
        )
    finally:
        await binance.close()

    bars = series.bars
    print(f"  Bars: {series.count}")

    # --- Precompute ---
    print("\n[2/4] Precomputing MarketContext + ATR...")
    t0 = time.time()
    contexts = precompute_contexts(series)
    atrs = precompute_atrs(bars)
    print(f"  Done in {time.time() - t0:.1f}s")

    # --- Build regime periods ---
    total_months = (data_end.year - data_start.year) * 12 + (data_end.month - data_start.month)
    boundaries = month_boundaries(2020, 1, total_months)

    periods = []
    i = 0
    while i + is_months + oos_months <= len(boundaries) - 1:
        is_start = boundaries[i]
        is_end = boundaries[i + is_months]
        oos_start = is_end
        oos_end_idx = i + is_months + oos_months
        if oos_end_idx >= len(boundaries):
            break
        oos_end = boundaries[oos_end_idx]
        periods.append({
            "id": len(periods) + 1,
            "is_start": is_start, "is_end": is_end,
            "oos_start": oos_start, "oos_end": oos_end,
        })
        i += oos_months

    if max_periods:
        periods = periods[:max_periods]

    print(f"\n[3/4] Running LLM WFO on {len(periods)} periods...")

    # --- LLM pipeline config ---
    llm = AnthropicClient(api_key=api_key)
    engine_config = EngineConfig(
        evolution=EvolutionConfig(
            symbol="BTCUSDT", timeframe="1h",
            generations=3, population_size=10,
        )
    )

    def pipeline_backtest(b, c, a, pattern, tf="1h"):
        return fast_backtest(b, c, a, pattern, timeframe=tf, annualize=False)

    registry = StrategyRegistry()

    # --- Run LLM arm ---
    arm_l_results = []
    total_cost = 0.0
    total_time = 0.0

    for p in periods:
        pid = p["id"]
        is_label = f"{p['is_start'].strftime('%Y-%m')} to {p['is_end'].strftime('%Y-%m')}"
        oos_label = f"{p['oos_start'].strftime('%Y-%m')} to {p['oos_end'].strftime('%Y-%m')}"
        print(f"\n  --- Period {pid}/{len(periods)}: IS {is_label}, OOS {oos_label} ---")

        _, is_s, is_e = slice_bars_by_date(bars, p["is_start"], p["is_end"])
        _, oos_s, oos_e = slice_bars_by_date(bars, p["oos_start"], p["oos_end"])

        if is_e - is_s < 30 or oos_e - oos_s < 10:
            print(f"    Skip: not enough bars (IS={is_e - is_s}, OOS={oos_e - oos_s})")
            arm_l_results.append({
                "period": pid, "oos_sharpe": 0.0, "reason": "insufficient bars",
                "num_hypotheses": 0, "graduated": 0, "dsr": None, "passed_dsr": False,
                "deployed": False, "tokens": 0, "novel_fields": [],
            })
            continue

        # Build IS OHLCVSeries for EvolutionEngine
        is_series = OHLCVSeries(
            symbol="BTCUSDT", timeframe=Timeframe.H1,
            bars=bars[is_s:is_e],
        )

        pipeline = LLMReEvolutionPipeline(
            llm=llm, engine_config=engine_config,
            backtest_fn=pipeline_backtest,
            min_oos_trades=3,
        )

        t_start = time.time()
        result = await pipeline.run(
            is_series=is_series,
            oos_bars=bars[oos_s:oos_e],
            oos_contexts=contexts[oos_s:oos_e],
            oos_atrs=atrs[oos_s:oos_e],
            registry=registry,
            version_id=f"LLM-V{pid}",
            metadata={"is_period": is_label, "oos_period": oos_label},
        )
        elapsed = time.time() - t_start
        total_time += elapsed

        # Estimate cost
        est_cost = result.total_llm_tokens * (0.6 * 3 + 0.4 * 15) / 1_000_000
        total_cost += est_cost

        oos_sharpe = result.oos_fitness.sharpe_ratio if result.oos_fitness else 0.0
        if not result.passed_dsr_gate:
            oos_sharpe = 0.0  # cash position if DSR fails

        print(f"    Hypotheses: {result.num_hypotheses}, Graduated: {result.num_graduated}")
        print(f"    OOS Sharpe: {oos_sharpe:.4f}, DSR: {result.dsr}, Passed: {result.passed_dsr_gate}")
        print(f"    Novel fields: {result.novel_fields}")
        print(f"    Tokens: {result.total_llm_tokens}, Cost: ${est_cost:.4f}, Time: {elapsed:.1f}s")
        print(f"    Reason: {result.reason}")

        arm_l_results.append({
            "period": pid,
            "oos_sharpe": oos_sharpe,
            "oos_sharpe_raw": result.oos_fitness.sharpe_ratio if result.oos_fitness else None,
            "reason": result.reason,
            "num_hypotheses": result.num_hypotheses,
            "graduated": result.num_graduated,
            "dsr": result.dsr,
            "dsr_pvalue": result.dsr_pvalue,
            "passed_dsr": result.passed_dsr_gate,
            "deployed": result.deployed,
            "tokens": result.total_llm_tokens,
            "cost_usd": round(est_cost, 4),
            "elapsed_s": round(elapsed, 1),
            "novel_fields": result.novel_fields,
            "all_fields": result.all_fields_used,
            "cumulative_M": registry.cumulative_trials,
        })

    await llm.close()

    # --- Combine with Exp 4a data ---
    print(f"\n[4/4] Analysis...")
    print(f"\n  Total LLM cost: ${total_cost:.4f}")
    print(f"  Total time: {total_time:.0f}s ({total_time / 60:.1f}min)")
    print(f"  Cumulative M: {registry.cumulative_trials}")

    # Extract OOS Sharpe arrays for comparison
    n_periods = len(arm_l_results)
    l_sharpes = [r["oos_sharpe"] for r in arm_l_results]

    # Get matching periods from Exp 4a
    g_sharpes = []
    a_sharpes = []
    b_sharpes = []
    for r in arm_l_results:
        pid = r["period"]
        idx = pid - 1
        if idx < len(exp4a_arms["arm_g"]):
            g_sharpes.append(exp4a_arms["arm_g"][idx].get("oos_sharpe", 0.0))
            a_sharpes.append(exp4a_arms["ctrl_a"][idx].get("oos_sharpe", 0.0))
            b_sharpes.append(exp4a_arms["ctrl_b"][idx].get("oos_sharpe", 0.0))
        else:
            g_sharpes.append(0.0)
            a_sharpes.append(0.0)
            b_sharpes.append(0.0)

    # --- Print comparison table ---
    print(f"\n{'Period':<8} {'Arm L':>8} {'Arm G':>8} {'Ctrl A':>8} {'Ctrl B':>8}  L>A  L>G  DSR")
    for i, r in enumerate(arm_l_results):
        l_gt_a = "Y" if l_sharpes[i] > a_sharpes[i] else "N"
        l_gt_g = "Y" if l_sharpes[i] > g_sharpes[i] else "N"
        dsr_str = "PASS" if r["passed_dsr"] else "FAIL"
        print(f"P{r['period']:<7} {l_sharpes[i]:>8.4f} {g_sharpes[i]:>8.4f} "
              f"{a_sharpes[i]:>8.4f} {b_sharpes[i]:>8.4f}  {l_gt_a:>3}  {l_gt_g:>3}  {dsr_str}")

    # --- Statistics ---
    mean_l = sum(l_sharpes) / n_periods if n_periods else 0
    mean_g = sum(g_sharpes) / n_periods if n_periods else 0
    mean_a = sum(a_sharpes) / n_periods if n_periods else 0

    l_gt_a_count = sum(1 for i in range(n_periods) if l_sharpes[i] > a_sharpes[i])
    l_gt_g_count = sum(1 for i in range(n_periods) if l_sharpes[i] > g_sharpes[i])
    dsr_pass_count = sum(1 for r in arm_l_results if r["passed_dsr"])

    print(f"\nMean Sharpe: L={mean_l:.4f}, G={mean_g:.4f}, A={mean_a:.4f}")
    print(f"L > A: {l_gt_a_count}/{n_periods} ({100 * l_gt_a_count / n_periods:.1f}%)")
    print(f"L > G: {l_gt_g_count}/{n_periods} ({100 * l_gt_g_count / n_periods:.1f}%)")
    print(f"DSR pass: {dsr_pass_count}/{n_periods} ({100 * dsr_pass_count / n_periods:.1f}%)")

    # Cohen's d
    d_l_vs_g = cohens_d(l_sharpes, g_sharpes)
    d_l_vs_a = cohens_d(l_sharpes, a_sharpes)
    print(f"\nCohen's d (L vs G): {d_l_vs_g:.3f}")
    print(f"Cohen's d (L vs A): {d_l_vs_a:.3f}")

    if n_periods >= 5:
        p_l_vs_a = wilcoxon_approx(l_sharpes, a_sharpes)
        p_l_vs_g = wilcoxon_approx(l_sharpes, g_sharpes)
        print(f"Wilcoxon p (L vs A): {p_l_vs_a:.4f}")
        print(f"Wilcoxon p (L vs G): {p_l_vs_g:.4f}")
    else:
        p_l_vs_a = p_l_vs_g = None

    # Novelty stats
    all_novel = set()
    for r in arm_l_results:
        all_novel.update(r.get("novel_fields", []))
    print(f"\nNovel fields across all periods: {sorted(all_novel)}")

    # --- Pilot decision ---
    if not args.full:
        print("\n" + "=" * 70)
        print("PILOT DECISION")
        print("=" * 70)
        if abs(d_l_vs_g) < 0.2:
            print(f"  Cohen's d = {d_l_vs_g:.3f} < 0.2 → SMALL effect")
            print("  Recommendation: Consider stopping. Effect too small to justify 23 periods.")
        elif abs(d_l_vs_g) < 0.5:
            print(f"  Cohen's d = {d_l_vs_g:.3f} → MEDIUM effect")
            print("  Recommendation: Continue to full 23 periods for statistical power.")
        else:
            print(f"  Cohen's d = {d_l_vs_g:.3f} → LARGE effect")
            print("  Recommendation: Strong signal. Continue to full 23 periods.")
        print("\n  ** Waiting for Sean's decision. Run with --full to continue. **")

    # --- Save results ---
    output = {
        "experiment": "Exp 4b LLM WFO",
        "mode": "full" if args.full else "pilot",
        "date": datetime.now(timezone.utc).isoformat(),
        "n_periods": n_periods,
        "total_cost_usd": round(total_cost, 4),
        "total_time_s": round(total_time, 1),
        "cumulative_M": registry.cumulative_trials,
        "summary": {
            "mean_sharpe_L": round(mean_l, 4),
            "mean_sharpe_G": round(mean_g, 4),
            "mean_sharpe_A": round(mean_a, 4),
            "L_gt_A_pct": round(100 * l_gt_a_count / n_periods, 1) if n_periods else 0,
            "L_gt_G_pct": round(100 * l_gt_g_count / n_periods, 1) if n_periods else 0,
            "DSR_pass_pct": round(100 * dsr_pass_count / n_periods, 1) if n_periods else 0,
            "cohens_d_L_vs_G": round(d_l_vs_g, 3),
            "cohens_d_L_vs_A": round(d_l_vs_a, 3),
            "wilcoxon_p_L_vs_A": round(p_l_vs_a, 4) if p_l_vs_a is not None else None,
            "wilcoxon_p_L_vs_G": round(p_l_vs_g, 4) if p_l_vs_g is not None else None,
            "novel_fields": sorted(all_novel),
        },
        "periods": arm_l_results,
    }

    output_path = Path(__file__).parent.parent.parent / "validation" / "llm_wfo_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\n  Results saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

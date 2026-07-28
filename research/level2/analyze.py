"""Level 2: Statistical Analysis of CUSUM experiment results.

Reads results.json, runs:
1. Paired t-tests (CUSUM vs each baseline)
2. Win rate (how often CUSUM has lower DD)
3. Bootstrap 95% CI on DD reduction vs BaseAgent
4. Cohen's d effect size
5. Per-market/timeframe consistency check

Usage: python research/level2/analyze.py
"""

from __future__ import annotations

import json
import os
import random
import sys
from math import sqrt
from statistics import mean, stdev
from typing import Dict, List

from scipy import stats

RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))


def load_results() -> List[Dict]:
    path = os.path.join(RESULTS_DIR, "results.json")
    if not os.path.exists(path):
        path = os.path.join(RESULTS_DIR, "results_partial.json")
    with open(path) as f:
        return json.load(f)


def paired_analysis(results: List[Dict]):
    """Paired comparison: CUSUM DD vs each baseline DD."""
    comparisons = {
        "vs_base": ("base", "No calibration"),
        "vs_periodic": ("periodic", "Periodic reduce"),
        "vs_random": ("random", "Random reduce"),
        "vs_simple_wr": ("simple_wr", "Simple WR threshold"),
    }

    print("=" * 70)
    print("PAIRED ANALYSIS: DD Reduction (positive = CUSUM better)")
    print("=" * 70)

    summary = {}
    for key, (agent_key, label) in comparisons.items():
        # DD difference: baseline_dd - cusum_dd (positive = CUSUM wins)
        diffs = []
        for r in results:
            a = r["agents"]
            diff = a[agent_key]["equity_dd"] - a["cusum"]["equity_dd"]
            diffs.append(diff)

        n = len(diffs)
        if n < 2:
            print(f"\n{key}: Not enough data (n={n})")
            continue

        mean_d = mean(diffs)
        std_d = stdev(diffs) if n > 1 else 0.001
        wins = sum(1 for d in diffs if d > 0)
        ties = sum(1 for d in diffs if d == 0)
        losses = n - wins - ties

        # Paired t-test (one-sided: CUSUM better, i.e. mean diff > 0)
        t_stat, p_two = stats.ttest_1samp(diffs, 0)
        p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2

        # Cohen's d
        d = mean_d / std_d if std_d > 0 else 0

        # Effect size interpretation
        if abs(d) < 0.2:
            effect = "negligible"
        elif abs(d) < 0.5:
            effect = "small"
        elif abs(d) < 0.8:
            effect = "medium"
        else:
            effect = "large"

        print(f"\n--- {key}: CUSUM vs {label} ---")
        print(f"  N = {n}")
        print(f"  Mean DD reduction: {mean_d:+.2f}")
        print(f"  Std:  {std_d:.2f}")
        print(f"  CUSUM wins: {wins}/{n} ({wins/n*100:.1f}%), ties: {ties}, losses: {losses}")
        print(f"  Paired t-test: t={t_stat:.4f}, p(one-sided)={p_one:.6f}")
        print(f"  Cohen's d: {d:.4f} ({effect})")

        summary[key] = {
            "n": n,
            "mean_dd_reduction": round(mean_d, 4),
            "std": round(std_d, 4),
            "win_rate": round(wins / n, 4),
            "wins": wins,
            "ties": ties,
            "losses": losses,
            "t_stat": round(t_stat, 4),
            "p_one_sided": round(p_one, 6),
            "cohens_d": round(d, 4),
            "effect_size": effect,
        }

    return summary


def bootstrap_ci(results: List[Dict], n_boot: int = 5000):
    """Bootstrap 95% CI on DD reduction vs BaseAgent."""
    diffs = [
        r["agents"]["base"]["equity_dd"] - r["agents"]["cusum"]["equity_dd"]
        for r in results
    ]

    rng = random.Random(42)
    boot_means = []
    for _ in range(n_boot):
        sample = [rng.choice(diffs) for _ in range(len(diffs))]
        boot_means.append(mean(sample))
    boot_means.sort()

    ci_lower = boot_means[int(0.025 * n_boot)]
    ci_upper = boot_means[int(0.975 * n_boot)]
    observed = mean(diffs)

    print(f"\n{'='*70}")
    print("BOOTSTRAP 95% CI: DD Reduction vs BaseAgent")
    print(f"{'='*70}")
    print(f"  Observed mean: {observed:+.2f}")
    print(f"  95% CI: [{ci_lower:+.2f}, {ci_upper:+.2f}]")
    print(f"  CI includes 0: {'YES' if ci_lower <= 0 <= ci_upper else 'NO'}")

    return {
        "observed_mean": round(observed, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "ci_includes_zero": ci_lower <= 0 <= ci_upper,
        "n_boot": n_boot,
    }


def per_market_breakdown(results: List[Dict]):
    """Consistency check: does CUSUM work on both markets?"""
    print(f"\n{'='*70}")
    print("PER-MARKET / PER-TIMEFRAME BREAKDOWN")
    print(f"{'='*70}")

    # Group by symbol and timeframe
    groups = {}
    for r in results:
        key = f"{r['symbol']}_{r['timeframe']}"
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    breakdown = {}
    for key, group in sorted(groups.items()):
        diffs = [
            r["agents"]["base"]["equity_dd"] - r["agents"]["cusum"]["equity_dd"]
            for r in group
        ]
        n = len(diffs)
        m = mean(diffs)
        wins = sum(1 for d in diffs if d > 0)

        if n >= 2:
            t_stat, p_two = stats.ttest_1samp(diffs, 0)
            p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2
        else:
            t_stat, p_one = 0, 1

        print(f"\n  {key}: N={n}, mean DD Δ={m:+.2f}, "
              f"CUSUM wins={wins}/{n} ({wins/n*100:.0f}%), "
              f"p={p_one:.4f}")

        breakdown[key] = {
            "n": n,
            "mean_dd_reduction": round(m, 4),
            "win_rate": round(wins / n, 4),
            "p_one_sided": round(p_one, 4),
        }

    return breakdown


def pnl_impact(results: List[Dict]):
    """Check if DD reduction comes at cost of PnL."""
    print(f"\n{'='*70}")
    print("PnL IMPACT: Does CUSUM hurt returns?")
    print(f"{'='*70}")

    pnl_diffs = [
        r["agents"]["cusum"]["equity_pnl"] - r["agents"]["base"]["equity_pnl"]
        for r in results
    ]
    n = len(pnl_diffs)
    m = mean(pnl_diffs)
    wins = sum(1 for d in pnl_diffs if d > 0)

    print(f"  Mean PnL change (CUSUM - Base): {m:+.2f}")
    print(f"  CUSUM PnL better: {wins}/{n} ({wins/n*100:.0f}%)")

    # On strategies where CUSUM reduced DD, did it also improve PnL?
    dd_diffs = [
        r["agents"]["base"]["equity_dd"] - r["agents"]["cusum"]["equity_dd"]
        for r in results
    ]
    dd_improved = [(dd, pnl) for dd, pnl in zip(dd_diffs, pnl_diffs) if dd > 0]
    if dd_improved:
        pnl_of_dd_winners = [p for _, p in dd_improved]
        pnl_better_too = sum(1 for p in pnl_of_dd_winners if p > 0)
        print(f"  Of {len(dd_improved)} DD-improved strategies: "
              f"{pnl_better_too} also improved PnL ({pnl_better_too/len(dd_improved)*100:.0f}%)")

    return {
        "mean_pnl_change": round(m, 4),
        "pnl_win_rate": round(wins / n, 4),
    }


def reduction_precision(results: List[Dict]):
    """How precise is CUSUM's lot reduction?"""
    print(f"\n{'='*70}")
    print("CUSUM REDUCTION STATS")
    print(f"{'='*70}")

    total_trades = 0
    total_reduced = 0
    for r in results:
        a = r["agents"]["cusum"]
        total_trades += a["trades"]
        total_reduced += a["reduced_lot_trades"]

    pct = total_reduced / max(total_trades, 1) * 100
    print(f"  Total trades: {total_trades}")
    print(f"  Reduced-lot trades: {total_reduced} ({pct:.1f}%)")

    # Compare reduction rates across agents
    for agent_key, label in [("periodic", "Periodic"), ("random", "Random"), ("simple_wr", "SimpleWR")]:
        reduced = sum(r["agents"][agent_key]["reduced_lot_trades"] for r in results)
        trades = sum(r["agents"][agent_key]["trades"] for r in results)
        pct = reduced / max(trades, 1) * 100
        print(f"  {label} reduced: {reduced}/{trades} ({pct:.1f}%)")


def pass_gate(summary: Dict, bootstrap: Dict, breakdown: Dict):
    """Evaluate Level 2 → Level 3 pass gates."""
    print(f"\n{'='*70}")
    print("PASS GATE: Level 2 → Level 3")
    print(f"{'='*70}")

    vs_base = summary.get("vs_base", {})
    vs_swr = summary.get("vs_simple_wr", {})

    gate1 = vs_base.get("win_rate", 0) > 0.55
    gate2 = vs_swr.get("p_one_sided", 1) < 0.1
    gate3 = bootstrap.get("ci_lower", 0) > 0
    gate4 = all(v.get("mean_dd_reduction", 0) > 0 for v in breakdown.values())

    print(f"  Gate 1: CUSUM vs Base win rate > 55%: "
          f"{'PASS' if gate1 else 'FAIL'} ({vs_base.get('win_rate', 0)*100:.1f}%)")
    print(f"  Gate 2: CUSUM vs SimpleWR p < 0.1: "
          f"{'PASS' if gate2 else 'FAIL'} (p={vs_swr.get('p_one_sided', 1):.6f})")
    print(f"  Gate 3: Bootstrap CI lower > 0: "
          f"{'PASS' if gate3 else 'FAIL'} (CI=[{bootstrap.get('ci_lower', 0):+.2f}, {bootstrap.get('ci_upper', 0):+.2f}])")
    print(f"  Gate 4: Per-market consistency: "
          f"{'PASS' if gate4 else 'FAIL'}")

    overall = gate1 and gate2 and gate3 and gate4
    verdict = "PASS → Proceed to Level 3" if overall else "FAIL → CUSUM does not generalize"
    print(f"\n  VERDICT: {verdict}")

    return {
        "gate1_win_rate": gate1,
        "gate2_vs_swr": gate2,
        "gate3_ci": gate3,
        "gate4_consistency": gate4,
        "overall": overall,
    }


def write_report(results: List[Dict], summary: Dict, bootstrap: Dict, breakdown: Dict, gates: Dict, pnl: Dict):
    """Write RESULTS.md report."""
    n = len(results)
    symbols = sorted(set(r["symbol"] for r in results))
    timeframes = sorted(set(r["timeframe"] for r in results))

    vs_base = summary.get("vs_base", {})
    vs_periodic = summary.get("vs_periodic", {})
    vs_random = summary.get("vs_random", {})
    vs_swr = summary.get("vs_simple_wr", {})

    report = f"""# Level 2: CUSUM Adaptive Position Sizing — Multi-Strategy Validation

**Date**: {datetime.now().strftime('%Y-%m-%d')}
**Goal**: Validate CUSUM-based lot reduction generalizes across strategies, symbols, timeframes.

---

## Research Question

Does CUSUM-based adaptive position sizing reduce drawdown compared to:
(a) No calibration (BaseAgent)
(b) Periodic lot reduction
(c) Random lot reduction
(d) Simple rolling WR threshold

## Setup

- **Symbols**: {', '.join(symbols)}
- **Timeframes**: {', '.join(timeframes)}
- **Strategies**: {n} (from parameter grid, filtered to IS trades >= {MIN_IS_TRADES})
- **IS/OOS**: {IS_RATIO*100:.0f}%/{(1-IS_RATIO)*100:.0f}% walk-forward
- **Data**: {DAYS} days ({DAYS/365:.1f} years)
- **Warm-start**: IS trades establish baseline WR for CUSUM and SimpleWR
- **CUSUM threshold**: 4.0
- **Lot reduction**: ×0.5 on alert (all agents use same reduction)

## Results

### DD Reduction vs BaseAgent

- Strategies tested: **{n}**
- CUSUM wins: **{vs_base.get('wins', 0)}/{n} ({vs_base.get('win_rate', 0)*100:.1f}%)**
- Mean DD reduction: **{vs_base.get('mean_dd_reduction', 0):+.2f}**
- Bootstrap 95% CI: **[{bootstrap.get('ci_lower', 0):+.2f}, {bootstrap.get('ci_upper', 0):+.2f}]**
- Paired t-test: t={vs_base.get('t_stat', 0):.4f}, p={vs_base.get('p_one_sided', 1):.6f}
- Cohen's d: {vs_base.get('cohens_d', 0):.4f} ({vs_base.get('effect_size', 'N/A')})

### vs Naive Baselines

| Comparison | CUSUM Win Rate | Mean DD Δ | p-value (one-sided) | Cohen's d |
|------------|---------------|-----------|---------------------|-----------|
| vs No calibration | {vs_base.get('win_rate', 0)*100:.1f}% | {vs_base.get('mean_dd_reduction', 0):+.2f} | {vs_base.get('p_one_sided', 1):.6f} | {vs_base.get('cohens_d', 0):.4f} ({vs_base.get('effect_size', '')}) |
| vs Periodic | {vs_periodic.get('win_rate', 0)*100:.1f}% | {vs_periodic.get('mean_dd_reduction', 0):+.2f} | {vs_periodic.get('p_one_sided', 1):.6f} | {vs_periodic.get('cohens_d', 0):.4f} ({vs_periodic.get('effect_size', '')}) |
| vs Random | {vs_random.get('win_rate', 0)*100:.1f}% | {vs_random.get('mean_dd_reduction', 0):+.2f} | {vs_random.get('p_one_sided', 1):.6f} | {vs_random.get('cohens_d', 0):.4f} ({vs_random.get('effect_size', '')}) |
| vs Simple WR | {vs_swr.get('win_rate', 0)*100:.1f}% | {vs_swr.get('mean_dd_reduction', 0):+.2f} | {vs_swr.get('p_one_sided', 1):.6f} | {vs_swr.get('cohens_d', 0):.4f} ({vs_swr.get('effect_size', '')}) |

### Per-Market / Per-Timeframe Breakdown

| Segment | N | Mean DD Δ | Win Rate | p-value |
|---------|---|-----------|----------|---------|
"""
    for key, v in sorted(breakdown.items()):
        report += f"| {key} | {v['n']} | {v['mean_dd_reduction']:+.2f} | {v['win_rate']*100:.0f}% | {v['p_one_sided']:.4f} |\n"

    report += f"""
### PnL Impact

- Mean PnL change (CUSUM - Base): **{pnl.get('mean_pnl_change', 0):+.2f}**
- CUSUM PnL better: {pnl.get('pnl_win_rate', 0)*100:.0f}%

## Pass Gate (Level 2 → Level 3)

| Gate | Criterion | Result |
|------|-----------|--------|
| 1 | CUSUM vs Base win rate > 55% | **{'PASS' if gates['gate1_win_rate'] else 'FAIL'}** ({vs_base.get('win_rate', 0)*100:.1f}%) |
| 2 | CUSUM vs SimpleWR p < 0.1 | **{'PASS' if gates['gate2_vs_swr'] else 'FAIL'}** (p={vs_swr.get('p_one_sided', 1):.6f}) |
| 3 | Bootstrap CI lower > 0 | **{'PASS' if gates['gate3_ci'] else 'FAIL'}** ([{bootstrap.get('ci_lower', 0):+.2f}, {bootstrap.get('ci_upper', 0):+.2f}]) |
| 4 | Per-market consistency | **{'PASS' if gates['gate4_consistency'] else 'FAIL'}** |

**VERDICT: {'PASS' if gates['overall'] else 'FAIL'}**

{'→ Proceed to Level 3: threshold optimization + real-money pilot design' if gates['overall'] else '→ CUSUM does not generalize. No paper. Consider SimpleWR as simpler alternative if it performs comparably.'}
"""

    path = os.path.join(RESULTS_DIR, "RESULTS.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nReport written: {path}")


if __name__ == "__main__":
    from datetime import datetime

    # Also need this for the report
    from run_matrix import DAYS, IS_RATIO, MIN_IS_TRADES

    results = load_results()
    print(f"Loaded {len(results)} results")

    summary = paired_analysis(results)
    bootstrap = bootstrap_ci(results)
    breakdown = per_market_breakdown(results)
    pnl = pnl_impact(results)
    reduction_precision(results)
    gates = pass_gate(summary, bootstrap, breakdown)
    write_report(results, summary, bootstrap, breakdown, gates, pnl)

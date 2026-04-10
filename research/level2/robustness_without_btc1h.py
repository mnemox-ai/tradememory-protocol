"""Robustness check: re-run analysis WITHOUT BTCUSDT 1h segment.

BTCUSDT 1h shows 100% CUSUM win rate which is suspiciously perfect.
This script filters it out and re-computes all statistics to see if
the aggregate results still hold.

Usage: python research/level2/robustness_without_btc1h.py
"""
from __future__ import annotations

import json
import os
import sys
from math import sqrt
from statistics import mean, stdev

from scipy import stats

RESULTS_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    path = os.path.join(RESULTS_DIR, "results.json")
    with open(path) as f:
        all_results = json.load(f)

    print(f"Total results: {len(all_results)}")

    # Filter out BTCUSDT 1h
    filtered = [r for r in all_results if not (r["symbol"] == "BTCUSDT" and r["timeframe"] == "1h")]
    print(f"After removing BTCUSDT 1h: {len(filtered)}")

    # --- vs BaseAgent ---
    diffs = [r["agents"]["base"]["equity_dd"] - r["agents"]["cusum"]["equity_dd"] for r in filtered]
    n = len(diffs)
    m = mean(diffs)
    s = stdev(diffs)
    wins = sum(1 for d in diffs if d > 0)
    t_stat, p_two = stats.ttest_1samp(diffs, 0)
    p_one = p_two / 2 if t_stat > 0 else 1 - p_two / 2
    d = m / s if s > 0 else 0

    print(f"\n=== CUSUM vs BaseAgent (WITHOUT BTCUSDT 1h) ===")
    print(f"  N = {n}")
    print(f"  CUSUM wins: {wins}/{n} ({wins/n*100:.1f}%)")
    print(f"  Mean DD reduction: {m:+.2f}")
    print(f"  Cohen's d: {d:.4f}")
    print(f"  p (one-sided): {p_one:.6f}")

    # --- vs SimpleWR ---
    diffs_swr = [r["agents"]["simple_wr"]["equity_dd"] - r["agents"]["cusum"]["equity_dd"] for r in filtered]
    m_swr = mean(diffs_swr)
    s_swr = stdev(diffs_swr)
    wins_swr = sum(1 for d in diffs_swr if d > 0)
    t_swr, p2_swr = stats.ttest_1samp(diffs_swr, 0)
    p_swr = p2_swr / 2 if t_swr > 0 else 1 - p2_swr / 2
    d_swr = m_swr / s_swr if s_swr > 0 else 0

    print(f"\n=== CUSUM vs SimpleWR (WITHOUT BTCUSDT 1h) ===")
    print(f"  CUSUM wins: {wins_swr}/{n} ({wins_swr/n*100:.1f}%)")
    print(f"  Mean DD reduction: {m_swr:+.2f}")
    print(f"  Cohen's d: {d_swr:.4f}")
    print(f"  p (one-sided): {p_swr:.6f}")

    # --- Bootstrap CI ---
    import random
    rng = random.Random(42)
    boot_means = []
    for _ in range(5000):
        sample = [rng.choice(diffs) for _ in range(n)]
        boot_means.append(mean(sample))
    boot_means.sort()
    ci_lo = boot_means[int(0.025 * 5000)]
    ci_hi = boot_means[int(0.975 * 5000)]
    print(f"\n=== Bootstrap 95% CI (vs Base, WITHOUT BTCUSDT 1h) ===")
    print(f"  [{ci_lo:+.2f}, {ci_hi:+.2f}]")
    print(f"  Includes 0: {'YES' if ci_lo <= 0 <= ci_hi else 'NO'}")

    # --- Per remaining segment ---
    print(f"\n=== Per-Segment Breakdown ===")
    groups = {}
    for r in filtered:
        key = f"{r['symbol']}_{r['timeframe']}"
        groups.setdefault(key, []).append(r)

    for key, group in sorted(groups.items()):
        seg_diffs = [r["agents"]["base"]["equity_dd"] - r["agents"]["cusum"]["equity_dd"] for r in group]
        seg_n = len(seg_diffs)
        seg_m = mean(seg_diffs)
        seg_wins = sum(1 for d in seg_diffs if d > 0)
        print(f"  {key}: N={seg_n}, mean DD Δ={seg_m:+.2f}, wins={seg_wins}/{seg_n} ({seg_wins/seg_n*100:.0f}%)")

    # Save results
    output = {
        "description": "Robustness check: aggregate stats WITHOUT BTCUSDT 1h",
        "n": n,
        "vs_base": {"win_rate": round(wins/n, 4), "mean_dd_reduction": round(m, 2), "cohens_d": round(d, 4), "p_one_sided": round(p_one, 6)},
        "vs_simple_wr": {"win_rate": round(wins_swr/n, 4), "mean_dd_reduction": round(m_swr, 2), "cohens_d": round(d_swr, 4), "p_one_sided": round(p_swr, 6)},
        "bootstrap_ci": {"lower": round(ci_lo, 2), "upper": round(ci_hi, 2)},
    }
    out_path = os.path.join(RESULTS_DIR, "robustness_no_btc1h.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()

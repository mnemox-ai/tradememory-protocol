#!/usr/bin/env python3
"""Permutation Test: Is memory-based filtering better than random filtering?

Core question: Memory skipped 36/48 trades and got Sharpe 9.57.
But what if we randomly skip 36/48 trades 1000 times?
If memory's Sharpe is only P50-P80, then memory has no real predictive power.

Test across all 4 OOS windows from the previous experiment.

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/experiment_permutation_test.py
"""

import asyncio
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.context_builder import ContextConfig
from tradememory.data.models import Timeframe
from scripts.strategy_definitions import build_strategy_e
from scripts.research.export_backtest_trades import (
    fast_backtest_with_trades,
    precompute_contexts,
    precompute_atrs,
)

SYMBOL = "BTCUSDT"
TIMEFRAME = Timeframe.H1
CONTEXT_CONFIG = ContextConfig(atr_period=14, trend_12h_bars=12, trend_24h_bars=24)
N_PERMUTATIONS = 1000

WINDOWS = [
    ("W1: 2024H1->2024H2",
     datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 6, 30, tzinfo=timezone.utc),
     datetime(2024, 7, 1, tzinfo=timezone.utc), datetime(2024, 12, 31, tzinfo=timezone.utc)),
    ("W2: 2024H2->2025H1",
     datetime(2024, 7, 1, tzinfo=timezone.utc), datetime(2024, 12, 31, tzinfo=timezone.utc),
     datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 6, 30, tzinfo=timezone.utc)),
    ("W3: 2025H1->2025H2",
     datetime(2025, 1, 1, tzinfo=timezone.utc), datetime(2025, 6, 30, tzinfo=timezone.utc),
     datetime(2025, 7, 1, tzinfo=timezone.utc), datetime(2025, 12, 31, tzinfo=timezone.utc)),
    ("W4: 2025H2->2026 (original)",
     datetime(2025, 6, 1, tzinfo=timezone.utc), datetime(2025, 11, 30, tzinfo=timezone.utc),
     datetime(2025, 12, 1, tzinfo=timezone.utc), datetime(2026, 3, 21, tzinfo=timezone.utc)),
]

# Memory config from original experiment (best)
@dataclass
class MemoryEntry:
    hour_utc: int
    trend_12h_pct: float
    regime: str
    atr_h1: float
    pnl_r: float


def context_similarity(mem, hour_utc, trend_12h_pct, regime, atr_h1):
    hour_score = 1.0 if mem.hour_utc == hour_utc else 0.0
    trend_sign_match = 1.0 if (mem.trend_12h_pct > 0) == (trend_12h_pct > 0) else 0.0
    trend_diff = abs(mem.trend_12h_pct - trend_12h_pct)
    trend_mag_score = max(0, 1.0 - trend_diff / 5.0)
    regime_score = 1.0 if mem.regime == regime else 0.3
    if mem.atr_h1 > 0 and atr_h1 > 0:
        atr_ratio = max(mem.atr_h1, atr_h1) / min(mem.atr_h1, atr_h1)
        atr_score = max(0, 1.0 - (atr_ratio - 1.0) / 2.0)
    else:
        atr_score = 0.5
    return (0.3 * hour_score + 0.2 * trend_sign_match +
            0.1 * trend_mag_score + 0.1 * regime_score + 0.1 * atr_score)


def memory_skip_indices(trades, contexts, atrs, memories, top_k=7):
    """Return set of trade indices that memory-based filter would skip."""
    skip = set()
    for idx, t in enumerate(trades):
        ctx = contexts[t.entry_bar] if t.entry_bar < len(contexts) else None
        atr_val = atrs[t.entry_bar] if t.entry_bar < len(atrs) else None
        if ctx is None:
            continue
        regime_str = str(ctx.regime.value) if ctx.regime and hasattr(ctx.regime, 'value') else str(ctx.regime)

        scored = []
        for mem in memories:
            sim = context_similarity(mem, ctx.hour_utc, ctx.trend_12h_pct or 0,
                                     regime_str, atr_val or 0)
            if sim >= 0.5:
                scored.append((mem, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        similar = scored[:top_k]

        if similar:
            neg_count = sum(1 for m, _ in similar if m.pnl_r < 0)
            if neg_count > len(similar) / 2:
                skip.add(idx)
    return skip


def compute_sharpe(trades, skip_indices):
    """Compute Sharpe for trades NOT in skip_indices."""
    kept = [t for i, t in enumerate(trades) if i not in skip_indices]
    if len(kept) < 2:
        return 0.0, 0.0, 0.0
    pnls = [t.pnl for t in kept]
    total_pnl = sum(pnls)
    avg = total_pnl / len(pnls)
    std = (sum((p - avg) ** 2 for p in pnls) / len(pnls)) ** 0.5
    sharpe = (avg / std * (252 * 24 / 6) ** 0.5) if std > 0 else 0
    wr = sum(1 for p in pnls if p > 0) / len(pnls)
    return sharpe, total_pnl, wr


def trades_to_memories(trades, contexts, atrs):
    memories = []
    for t in trades:
        ctx = contexts[t.entry_bar] if t.entry_bar < len(contexts) else None
        atr_val = atrs[t.entry_bar] if t.entry_bar < len(atrs) else None
        if ctx is None or atr_val is None or atr_val <= 0:
            continue
        pnl_r = (t.exit_price - t.entry_price) / atr_val
        if t.direction == "short":
            pnl_r = -pnl_r
        memories.append(MemoryEntry(
            hour_utc=ctx.hour_utc or 0,
            trend_12h_pct=ctx.trend_12h_pct or 0,
            regime=str(ctx.regime.value) if ctx.regime and hasattr(ctx.regime, 'value') else str(ctx.regime),
            atr_h1=atr_val,
            pnl_r=pnl_r,
        ))
    return memories


async def main():
    print("=" * 70)
    print("  PERMUTATION TEST: Memory vs Random Filtering")
    print(f"  {N_PERMUTATIONS} random permutations per window")
    print("  Question: Is memory better than randomly skipping the same # trades?")
    print("=" * 70)

    ds = BinanceDataSource()
    strategy = build_strategy_e()
    all_results = []

    try:
        for label, train_s, train_e, test_s, test_e in WINDOWS:
            print(f"\n{'='*70}")
            print(f"  {label}")
            print(f"{'='*70}")

            # Fetch + precompute
            train_data = await ds.fetch_ohlcv(SYMBOL, TIMEFRAME, train_s, train_e)
            test_data = await ds.fetch_ohlcv(SYMBOL, TIMEFRAME, test_s, test_e)
            print(f"  Train: {len(train_data.bars)} bars | Test: {len(test_data.bars)} bars")

            train_ctx = precompute_contexts(train_data, CONTEXT_CONFIG)
            train_atrs = precompute_atrs(train_data.bars, CONTEXT_CONFIG.atr_period)
            test_ctx = precompute_contexts(test_data, CONTEXT_CONFIG)
            test_atrs = precompute_atrs(test_data.bars, CONTEXT_CONFIG.atr_period)

            # Training -> memories
            train_fit, train_trades = fast_backtest_with_trades(
                train_data.bars, train_ctx, train_atrs, strategy,
                config=CONTEXT_CONFIG, timeframe="1h"
            )
            memories = trades_to_memories(train_trades, train_ctx, train_atrs)
            print(f"  Memories: {len(memories)}")

            # Baseline on test
            base_fit, base_trades = fast_backtest_with_trades(
                test_data.bars, test_ctx, test_atrs, strategy,
                config=CONTEXT_CONFIG, timeframe="1h"
            )
            n_trades = len(base_trades)
            base_sharpe = base_fit.sharpe_ratio
            print(f"  Baseline: {n_trades} trades | Sharpe {base_sharpe:.2f} | "
                  f"PnL ${base_fit.total_pnl:.2f}")

            if n_trades < 5:
                print("  (too few trades, skipping)")
                all_results.append({"window": label, "skip": True})
                continue

            # Memory-based skip
            mem_skip = memory_skip_indices(base_trades, test_ctx, test_atrs, memories)
            n_skip = len(mem_skip)
            mem_sharpe, mem_pnl, mem_wr = compute_sharpe(base_trades, mem_skip)
            print(f"  Memory filter: skip {n_skip}/{n_trades} | "
                  f"Sharpe {mem_sharpe:.2f} | PnL ${mem_pnl:.2f} | WR {mem_wr:.0%}")

            if n_skip == 0:
                print("  (memory skips 0 trades, nothing to permute)")
                all_results.append({
                    "window": label, "skip": False, "n_trades": n_trades,
                    "n_skip": 0, "memory_sharpe": round(mem_sharpe, 2),
                    "note": "memory_skips_nothing"
                })
                continue

            # ── Permutation test ──
            print(f"\n  Running {N_PERMUTATIONS} random permutations (skip {n_skip}/{n_trades})...")
            random_sharpes = []
            random_pnls = []
            trade_indices = list(range(n_trades))

            for p in range(N_PERMUTATIONS):
                random_skip = set(random.sample(trade_indices, n_skip))
                r_sharpe, r_pnl, _ = compute_sharpe(base_trades, random_skip)
                random_sharpes.append(r_sharpe)
                random_pnls.append(r_pnl)

            # Compute percentile of memory result
            sharpe_rank = sum(1 for s in random_sharpes if s < mem_sharpe)
            sharpe_percentile = sharpe_rank / N_PERMUTATIONS * 100

            pnl_rank = sum(1 for p in random_pnls if p < mem_pnl)
            pnl_percentile = pnl_rank / N_PERMUTATIONS * 100

            random_sharpes_sorted = sorted(random_sharpes)
            p5 = random_sharpes_sorted[int(N_PERMUTATIONS * 0.05)]
            p25 = random_sharpes_sorted[int(N_PERMUTATIONS * 0.25)]
            p50 = random_sharpes_sorted[int(N_PERMUTATIONS * 0.50)]
            p75 = random_sharpes_sorted[int(N_PERMUTATIONS * 0.75)]
            p95 = random_sharpes_sorted[int(N_PERMUTATIONS * 0.95)]
            avg_random = sum(random_sharpes) / len(random_sharpes)

            print(f"\n  Random Sharpe distribution (N={N_PERMUTATIONS}):")
            print(f"    P5={p5:.2f}  P25={p25:.2f}  P50={p50:.2f}  "
                  f"P75={p75:.2f}  P95={p95:.2f}  Mean={avg_random:.2f}")
            print(f"\n  Memory Sharpe: {mem_sharpe:.2f}")
            print(f"  Memory Percentile: P{sharpe_percentile:.1f} (Sharpe) | "
                  f"P{pnl_percentile:.1f} (PnL)")

            if sharpe_percentile >= 95:
                verdict = "SIGNIFICANT (P>=95): Memory has real predictive power"
            elif sharpe_percentile >= 80:
                verdict = "SUGGESTIVE (P80-95): Some signal but not conclusive"
            elif sharpe_percentile >= 50:
                verdict = "NOT SIGNIFICANT (P50-80): Memory no better than random"
            else:
                verdict = "WORSE THAN RANDOM (P<50): Memory hurts performance"

            print(f"\n  >> {verdict}")

            all_results.append({
                "window": label,
                "n_trades": n_trades,
                "n_skip": n_skip,
                "baseline_sharpe": round(base_sharpe, 2),
                "memory_sharpe": round(mem_sharpe, 2),
                "memory_pnl": round(mem_pnl, 2),
                "sharpe_percentile": round(sharpe_percentile, 1),
                "pnl_percentile": round(pnl_percentile, 1),
                "random_sharpe_dist": {
                    "p5": round(p5, 2), "p25": round(p25, 2),
                    "p50": round(p50, 2), "p75": round(p75, 2),
                    "p95": round(p95, 2), "mean": round(avg_random, 2),
                },
                "verdict": verdict,
            })

    finally:
        await ds.close()

    # ── Final summary ──
    print(f"\n\n{'='*70}")
    print(f"  PERMUTATION TEST SUMMARY")
    print(f"{'='*70}")
    print(f"\n  {'Window':<35} {'Skip':>6} {'Mem Sharpe':>12} {'Percentile':>12} {'Verdict':>15}")
    print(f"  {'-'*80}")

    for r in all_results:
        if r.get("skip") or r.get("note") == "memory_skips_nothing":
            print(f"  {r['window']:<35} {'N/A':>6} {'N/A':>12} {'N/A':>12} {'(no skip)':>15}")
            continue
        p = r["sharpe_percentile"]
        tag = "***" if p >= 95 else "**" if p >= 80 else "*" if p >= 50 else ""
        print(f"  {r['window']:<35} {r['n_skip']:>3}/{r['n_trades']:<2} "
              f"{r['memory_sharpe']:>11.2f} "
              f"P{p:<10.1f} {tag:>15}")

    sig_count = sum(1 for r in all_results
                    if not r.get("skip") and r.get("note") != "memory_skips_nothing"
                    and r.get("sharpe_percentile", 0) >= 95)
    testable = sum(1 for r in all_results
                   if not r.get("skip") and r.get("note") != "memory_skips_nothing")

    print(f"\n  Significant (P>=95): {sig_count}/{testable} windows")

    if sig_count == testable and testable > 0:
        print(f"\n  >> CONCLUSION: Memory has REAL predictive power across all regimes")
    elif sig_count > 0:
        print(f"\n  >> CONCLUSION: Memory has predictive power in SOME regimes ({sig_count}/{testable})")
    else:
        print(f"\n  >> CONCLUSION: Memory is NOT better than random filtering")
        print(f"     The Sharpe improvement comes from skipping trades (lower variance),")
        print(f"     not from memory's ability to identify bad trades.")

    # Save
    output_path = Path(__file__).parent / "output" / "memory_permutation_test.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment": "memory_permutation_test",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_permutations": N_PERMUTATIONS,
            "symbol": SYMBOL,
            "strategy": "Strategy E (Afternoon Engine)",
            "memory_config": "majority_negative, k=7, sim>=0.5",
            "windows": all_results,
            "significant_count": sig_count,
            "testable_count": testable,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Strict OOS validation of memory injection.

Two-level validation:
  Level 1: FIXED CONFIG — apply the best config from the original experiment
           (majority_negative, k=7, sim>=0.5) to NEW time windows without
           re-optimizing. If it works -> real signal. If not -> overfit.

  Level 2: FRESH SEARCH — let the agent re-search in each window independently.
           If different windows find different optimal configs -> regime-specific.
           If they converge -> robust.

Windows (non-overlapping train/test):
  W1: Train 2024-01~2024-06 -> Test 2024-07~2024-12 (pre-bull)
  W2: Train 2024-06~2024-12 -> Test 2025-01~2025-06 (bull run)
  W3: Train 2025-01~2025-06 -> Test 2025-07~2025-12 (mid cycle)
  W4: Train 2025-06~2025-11 -> Test 2025-12~2026-03 (original window, for comparison)

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/experiment_memory_oos.py
"""

import asyncio
import json
import math
import random
import sys
from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
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
    ("W4: 2025-Jun~Nov->2025-Dec~2026-Mar (original)",
     datetime(2025, 6, 1, tzinfo=timezone.utc), datetime(2025, 11, 30, tzinfo=timezone.utc),
     datetime(2025, 12, 1, tzinfo=timezone.utc), datetime(2026, 3, 21, tzinfo=timezone.utc)),
]

# Best config from original experiment (iter 6)
FIXED_CONFIG = {
    "similarity_cutoff": 0.5,
    "negative_threshold": -0.5,
    "top_k": 7,
    "w_hour": 0.3,
    "w_trend_dir": 0.2,
    "w_trend_mag": 0.1,
    "w_regime": 0.1,
    "w_atr": 0.1,
    "skip_logic": "majority_negative",
}

AGENT_ITERATIONS = 12  # per window for fresh search


# ── Memory Config ───────────────────────────────────
@dataclass
class MemoryConfig:
    similarity_cutoff: float = 0.5
    negative_threshold: float = -0.5
    top_k: int = 5
    w_hour: float = 0.3
    w_trend_dir: float = 0.25
    w_trend_mag: float = 0.15
    w_regime: float = 0.15
    w_atr: float = 0.15
    skip_logic: str = "avg_negative"

    def describe(self) -> str:
        return (f"sim>={self.similarity_cutoff:.2f} k={self.top_k} "
                f"skip={self.skip_logic}")


@dataclass
class MemoryEntry:
    hour_utc: int
    trend_12h_pct: float
    regime: str
    atr_h1: float
    pnl_r: float


# ── Core functions ──────────────────────────────────
def context_similarity(mem, hour_utc, trend_12h_pct, regime, atr_h1, cfg):
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
    return (cfg.w_hour * hour_score + cfg.w_trend_dir * trend_sign_match +
            cfg.w_trend_mag * trend_mag_score + cfg.w_regime * regime_score +
            cfg.w_atr * atr_score)


def should_skip_trade(memories, hour_utc, trend_12h_pct, regime, atr_h1, cfg):
    scored = []
    for mem in memories:
        sim = context_similarity(mem, hour_utc, trend_12h_pct, regime, atr_h1, cfg)
        if sim >= cfg.similarity_cutoff:
            scored.append((mem, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    similar = scored[:cfg.top_k]
    if not similar:
        return False

    if cfg.skip_logic == "avg_negative":
        total_w = sum(s for _, s in similar)
        if total_w == 0:
            return False
        weighted_pnl = sum(m.pnl_r * s for m, s in similar) / total_w
        return weighted_pnl < cfg.negative_threshold

    elif cfg.skip_logic == "majority_negative":
        neg_count = sum(1 for m, _ in similar if m.pnl_r < 0)
        return neg_count > len(similar) / 2

    return False


def evaluate_with_memory(baseline_trades, test_contexts, test_atrs, memories, cfg):
    skipped_bars = set()
    skip_w = skip_l = 0
    for t in baseline_trades:
        ctx = test_contexts[t.entry_bar] if t.entry_bar < len(test_contexts) else None
        atr_val = test_atrs[t.entry_bar] if t.entry_bar < len(test_atrs) else None
        if ctx is None:
            continue
        regime_str = str(ctx.regime.value) if ctx.regime and hasattr(ctx.regime, 'value') else str(ctx.regime)
        if should_skip_trade(memories, ctx.hour_utc, ctx.trend_12h_pct or 0,
                             regime_str, atr_val or 0, cfg):
            skipped_bars.add(t.entry_bar)
            if t.pnl > 0:
                skip_w += 1
            else:
                skip_l += 1

    kept = [t for t in baseline_trades if t.entry_bar not in skipped_bars]
    skipped_pnl = sum(t.pnl for t in baseline_trades if t.entry_bar in skipped_bars)

    if not kept:
        return {"trades": 0, "wr": 0, "pf": 0, "pnl": 0, "sharpe": 0,
                "dd": 0, "skipped": len(skipped_bars), "skipped_pnl": skipped_pnl,
                "skip_w": skip_w, "skip_l": skip_l}

    wins = [t for t in kept if t.pnl > 0]
    losses = [t for t in kept if t.pnl <= 0]
    total_pnl = sum(t.pnl for t in kept)
    wr = len(wins) / len(kept)
    gp = sum(t.pnl for t in wins) if wins else 0
    gl = abs(sum(t.pnl for t in losses)) if losses else 0.001
    pf = gp / gl if gl > 0 else float('inf')

    pnls = [t.pnl for t in kept]
    avg = sum(pnls) / len(pnls)
    std = (sum((p - avg) ** 2 for p in pnls) / len(pnls)) ** 0.5
    sharpe = (avg / std * (252 * 24 / 6) ** 0.5) if std > 0 else 0

    cum = peak = dd = 0
    for t in kept:
        cum += t.pnl
        peak = max(peak, cum)
        d = (peak - cum) / max(peak, 1) * 100
        dd = max(dd, d)

    return {"trades": len(kept), "wr": wr, "pf": pf, "pnl": total_pnl,
            "sharpe": sharpe, "dd": dd, "skipped": len(skipped_bars),
            "skipped_pnl": skipped_pnl, "skip_w": skip_w, "skip_l": skip_l}


# ── Agent (same as original, compact) ──────────────
def agent_search(baseline_trades, test_contexts, test_atrs, memories, iterations):
    """Run agent search, return best config and its metrics."""
    explore_configs = [
        MemoryConfig(),
        MemoryConfig(similarity_cutoff=0.7, negative_threshold=-0.3, top_k=3),
        MemoryConfig(similarity_cutoff=0.3, negative_threshold=-1.0, top_k=10),
        MemoryConfig(w_hour=0.6, w_trend_dir=0.15, w_trend_mag=0.1, w_regime=0.1, w_atr=0.05),
        MemoryConfig(skip_logic="majority_negative", top_k=7),
        MemoryConfig(skip_logic="majority_negative", top_k=5, similarity_cutoff=0.6),
        MemoryConfig(w_atr=0.5, w_hour=0.15, w_trend_dir=0.15, w_trend_mag=0.1, w_regime=0.1),
        MemoryConfig(similarity_cutoff=0.4, skip_logic="majority_negative", top_k=9),
    ]

    best_sharpe = -999
    best_cfg = None
    best_metrics = None
    log = []

    for i in range(iterations):
        if i < len(explore_configs):
            cfg = explore_configs[i]
        elif best_cfg:
            cfg = deepcopy(best_cfg)
            param = random.choice(["similarity_cutoff", "top_k", "skip_logic", "w_hour"])
            if param == "similarity_cutoff":
                cfg.similarity_cutoff = max(0.2, min(0.9, cfg.similarity_cutoff + random.uniform(-0.15, 0.15)))
            elif param == "top_k":
                cfg.top_k = max(1, min(15, cfg.top_k + random.randint(-3, 3)))
            elif param == "skip_logic":
                cfg.skip_logic = "majority_negative" if cfg.skip_logic == "avg_negative" else "avg_negative"
            elif param == "w_hour":
                cfg.w_hour = max(0.05, min(0.8, cfg.w_hour + random.uniform(-0.15, 0.15)))
        else:
            cfg = MemoryConfig()

        m = evaluate_with_memory(baseline_trades, test_contexts, test_atrs, memories, cfg)
        verdict = "KEEP" if m["sharpe"] > best_sharpe else "DISCARD"
        if m["sharpe"] > best_sharpe:
            best_sharpe = m["sharpe"]
            best_cfg = deepcopy(cfg)
            best_metrics = m

        log.append({"iter": i + 1, "config": cfg.describe(), "sharpe": round(m["sharpe"], 2),
                     "pnl": round(m["pnl"], 2), "skipped": m["skipped"], "verdict": verdict})

    return best_cfg, best_metrics, log


# ── Generate memories from training trades ──────────
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


# ── Main ────────────────────────────────────────────
async def main():
    print("=" * 70)
    print("  STRICT OOS VALIDATION: Memory Injection")
    print("  4 non-overlapping windows x 2 levels (fixed + fresh search)")
    print("=" * 70)

    ds = BinanceDataSource()
    strategy = build_strategy_e()
    fixed_cfg = MemoryConfig(**FIXED_CONFIG)

    all_results = []

    try:
        for label, train_s, train_e, test_s, test_e in WINDOWS:
            print(f"\n{'='*70}")
            print(f"  {label}")
            print(f"  Train: {train_s.date()} -> {train_e.date()}")
            print(f"  Test:  {test_s.date()} -> {test_e.date()}")
            print(f"{'='*70}")

            # Fetch data
            train_data = await ds.fetch_ohlcv(SYMBOL, TIMEFRAME, train_s, train_e)
            test_data = await ds.fetch_ohlcv(SYMBOL, TIMEFRAME, test_s, test_e)
            print(f"  Train bars: {len(train_data.bars)} | Test bars: {len(test_data.bars)}")

            # Precompute
            train_ctx = precompute_contexts(train_data, CONTEXT_CONFIG)
            train_atrs = precompute_atrs(train_data.bars, CONTEXT_CONFIG.atr_period)
            test_ctx = precompute_contexts(test_data, CONTEXT_CONFIG)
            test_atrs = precompute_atrs(test_data.bars, CONTEXT_CONFIG.atr_period)

            # Training trades -> memories
            train_fit, train_trades = fast_backtest_with_trades(
                train_data.bars, train_ctx, train_atrs, strategy,
                config=CONTEXT_CONFIG, timeframe="1h"
            )
            memories = trades_to_memories(train_trades, train_ctx, train_atrs)
            pos_mem = sum(1 for m in memories if m.pnl_r > 0)
            print(f"  Train: {train_fit.trade_count} trades, WR {train_fit.win_rate:.0%}, "
                  f"Sharpe {train_fit.sharpe_ratio:.2f}")
            print(f"  Memories: {len(memories)} (pos {pos_mem}, neg {len(memories)-pos_mem})")

            # Baseline on test
            base_fit, base_trades = fast_backtest_with_trades(
                test_data.bars, test_ctx, test_atrs, strategy,
                config=CONTEXT_CONFIG, timeframe="1h"
            )
            print(f"\n  Baseline: {base_fit.trade_count} trades | WR {base_fit.win_rate:.0%} | "
                  f"PF {base_fit.profit_factor:.2f} | Sharpe {base_fit.sharpe_ratio:.2f} | "
                  f"PnL ${base_fit.total_pnl:.2f}")

            if not base_trades:
                print("  (no trades, skipping)")
                all_results.append({"window": label, "baseline_trades": 0, "skip": True})
                continue

            # ── Level 1: Fixed config (no re-optimization) ──
            print(f"\n  [L1] FIXED CONFIG: {fixed_cfg.describe()}")
            l1 = evaluate_with_memory(base_trades, test_ctx, test_atrs, memories, fixed_cfg)
            l1_sharpe_delta = l1["sharpe"] - base_fit.sharpe_ratio
            l1_pnl_delta = l1["pnl"] - base_fit.total_pnl
            filter_ok = "+" if l1["skip_l"] >= l1["skip_w"] else "-"
            print(f"       Trades: {l1['trades']}/{base_fit.trade_count} | "
                  f"WR {l1['wr']:.0%} | PF {l1['pf']:.2f} | "
                  f"Sharpe {l1['sharpe']:.2f} ({l1_sharpe_delta:+.2f}) | "
                  f"PnL ${l1['pnl']:.2f} ({l1_pnl_delta:+.2f})")
            print(f"       Skipped: {l1['skipped']} ({filter_ok} L{l1['skip_l']}/W{l1['skip_w']}) "
                  f"PnL ${l1['skipped_pnl']:+.2f}")
            l1_pass = l1_sharpe_delta > 0 and l1["skip_l"] >= l1["skip_w"]
            print(f"       {'PASS' if l1_pass else 'FAIL'}")

            # ── Level 2: Fresh agent search ──
            print(f"\n  [L2] FRESH SEARCH ({AGENT_ITERATIONS} iterations)...")
            best_cfg, l2, search_log = agent_search(
                base_trades, test_ctx, test_atrs, memories, AGENT_ITERATIONS
            )
            if l2:
                l2_sharpe_delta = l2["sharpe"] - base_fit.sharpe_ratio
                l2_pnl_delta = l2["pnl"] - base_fit.total_pnl
                f2 = "+" if l2["skip_l"] >= l2["skip_w"] else "-"
                print(f"       Best: {best_cfg.describe()}")
                print(f"       Trades: {l2['trades']}/{base_fit.trade_count} | "
                      f"WR {l2['wr']:.0%} | PF {l2['pf']:.2f} | "
                      f"Sharpe {l2['sharpe']:.2f} ({l2_sharpe_delta:+.2f}) | "
                      f"PnL ${l2['pnl']:.2f} ({l2_pnl_delta:+.2f})")
                print(f"       Skipped: {l2['skipped']} ({f2} L{l2['skip_l']}/W{l2['skip_w']}) "
                      f"PnL ${l2['skipped_pnl']:+.2f}")
                l2_pass = l2_sharpe_delta > 0 and l2["skip_l"] >= l2["skip_w"]
                print(f"       {'PASS' if l2_pass else 'FAIL'}")
            else:
                l2_sharpe_delta = l2_pnl_delta = 0
                l2_pass = False
                best_cfg = None

            all_results.append({
                "window": label,
                "baseline_trades": base_fit.trade_count,
                "baseline_sharpe": round(base_fit.sharpe_ratio, 2),
                "baseline_pnl": round(base_fit.total_pnl, 2),
                "baseline_wr": round(base_fit.win_rate, 4),
                "memories": len(memories),
                "mem_pos_ratio": round(pos_mem / max(len(memories), 1), 2),
                "L1_fixed": {
                    "sharpe": round(l1["sharpe"], 2),
                    "sharpe_delta": round(l1_sharpe_delta, 2),
                    "pnl": round(l1["pnl"], 2),
                    "pnl_delta": round(l1_pnl_delta, 2),
                    "wr": round(l1["wr"], 4),
                    "skipped": l1["skipped"],
                    "skip_losers": l1["skip_l"],
                    "skip_winners": l1["skip_w"],
                    "pass": l1_pass,
                },
                "L2_search": {
                    "best_config": best_cfg.describe() if best_cfg else None,
                    "sharpe": round(l2["sharpe"], 2) if l2 else 0,
                    "sharpe_delta": round(l2_sharpe_delta, 2),
                    "pnl": round(l2["pnl"], 2) if l2 else 0,
                    "pnl_delta": round(l2_pnl_delta, 2),
                    "skipped": l2["skipped"] if l2 else 0,
                    "pass": l2_pass,
                    "search_log": search_log,
                },
            })

    finally:
        await ds.close()

    # ── Final verdict ──
    print(f"\n\n{'='*70}")
    print(f"  FINAL VERDICT")
    print(f"{'='*70}")

    print(f"\n  {'Window':<40} {'L1 Fixed':>12} {'L2 Search':>12}")
    print(f"  {'-'*64}")

    l1_passes = l2_passes = total = 0
    for r in all_results:
        if r.get("skip"):
            print(f"  {r['window']:<40} {'(no trades)':>12} {'(no trades)':>12}")
            continue
        total += 1
        l1_v = "PASS" if r["L1_fixed"]["pass"] else "FAIL"
        l2_v = "PASS" if r["L2_search"]["pass"] else "FAIL"
        l1_s = f"{r['L1_fixed']['sharpe_delta']:+.2f}"
        l2_s = f"{r['L2_search']['sharpe_delta']:+.2f}"
        if r["L1_fixed"]["pass"]:
            l1_passes += 1
        if r["L2_search"]["pass"]:
            l2_passes += 1
        print(f"  {r['window']:<40} {l1_v} ({l1_s}){'':<2} {l2_v} ({l2_s})")

    print(f"\n  L1 (Fixed config, true OOS): {l1_passes}/{total} windows pass")
    print(f"  L2 (Fresh search per window): {l2_passes}/{total} windows pass")

    if l1_passes >= total * 0.75:
        print(f"\n  >> ROBUST: Fixed config generalizes across regimes")
    elif l1_passes >= total * 0.5:
        print(f"\n  >> PARTIAL: Memory helps in some regimes, not all")
    elif l2_passes > l1_passes:
        print(f"\n  >> REGIME-SPECIFIC: Memory helps but config must be re-tuned per regime")
    else:
        print(f"\n  >> REJECTED: Memory injection does not reliably improve trading")

    # Save
    output_path = Path(__file__).parent / "output" / "memory_oos_validation.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment": "memory_injection_oos_validation",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbol": SYMBOL,
            "strategy": "Strategy E (Afternoon Engine)",
            "fixed_config": FIXED_CONFIG,
            "windows": all_results,
            "summary": {
                "l1_passes": l1_passes,
                "l2_passes": l2_passes,
                "total_windows": total,
            },
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Results saved: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

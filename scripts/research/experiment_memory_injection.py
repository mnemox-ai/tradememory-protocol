#!/usr/bin/env python3
"""Autoresearch-style autonomous experiment: Memory-Enhanced Trading.

Design (autoresearch paradigm):
  1. Read program.md for research objective
  2. Run baseline (no memory) -> establish benchmark
  3. Agent loop: propose memory config -> backtest -> evaluate -> keep/discard -> repeat
  4. Each iteration the agent adapts based on what worked/failed
  5. Output: research journal + best configuration found

The "agent" here is a systematic search that adapts its exploration based on
results — like autoresearch but without LLM API calls. Each iteration modifies
the memory injection parameters, backtests, and decides keep/discard.

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/experiment_memory_injection.py
    python scripts/research/experiment_memory_injection.py --iterations 30
"""

import asyncio
import json
import math
import random
import sys
from copy import deepcopy
from dataclasses import dataclass, field, asdict
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


# ── Config ──────────────────────────────────────────
SYMBOL = "BTCUSDT"
TIMEFRAME = Timeframe.H1

# Fixed window (from program.md)
TRAIN_START = datetime(2025, 6, 1, tzinfo=timezone.utc)
TRAIN_END = datetime(2025, 11, 30, tzinfo=timezone.utc)
TEST_START = datetime(2025, 12, 1, tzinfo=timezone.utc)
TEST_END = datetime(2026, 3, 21, tzinfo=timezone.utc)

CONTEXT_CONFIG = ContextConfig(atr_period=14, trend_12h_bars=12, trend_24h_bars=24)
DEFAULT_ITERATIONS = 20


# ── Memory Configuration (what the agent modifies) ──
@dataclass
class MemoryConfig:
    """Parameters the agent tunes each iteration."""
    similarity_cutoff: float = 0.5
    negative_threshold: float = -0.5  # skip if weighted avg PnL_R < this
    top_k: int = 5
    # Context dimension weights (must sum to ~1.0)
    w_hour: float = 0.3
    w_trend_dir: float = 0.25
    w_trend_mag: float = 0.15
    w_regime: float = 0.15
    w_atr: float = 0.15
    # Skip logic: "avg_negative" or "majority_negative"
    skip_logic: str = "avg_negative"

    def describe(self) -> str:
        return (f"sim>={self.similarity_cutoff:.2f} neg<{self.negative_threshold:.1f} "
                f"k={self.top_k} skip={self.skip_logic} "
                f"w=[h{self.w_hour:.1f} td{self.w_trend_dir:.1f} "
                f"tm{self.w_trend_mag:.1f} r{self.w_regime:.1f} a{self.w_atr:.1f}]")


# ── Memory Entry ────────────────────────────────────
@dataclass
class MemoryEntry:
    hour_utc: int
    trend_12h_pct: float
    regime: str
    atr_h1: float
    pnl_r: float  # PnL in R-multiples

    @property
    def outcome_weight(self) -> float:
        return 1.0 / (1.0 + math.exp(-2.0 * self.pnl_r))


# ── Experiment Result ───────────────────────────────
@dataclass
class ExperimentResult:
    iteration: int
    config: MemoryConfig
    trades: int
    kept_trades: int
    skipped: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    sharpe: float
    max_dd_pct: float
    skipped_pnl: float
    skipped_winners: int
    skipped_losers: int
    verdict: str  # "KEEP" or "DISCARD"
    reason: str


# ── Core functions ──────────────────────────────────
def context_similarity(mem: MemoryEntry, hour_utc: int, trend_12h_pct: float,
                       regime: str, atr_h1: float, cfg: MemoryConfig) -> float:
    """Weighted similarity using agent-tuned weights."""
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

    return (cfg.w_hour * hour_score +
            cfg.w_trend_dir * trend_sign_match +
            cfg.w_trend_mag * trend_mag_score +
            cfg.w_regime * regime_score +
            cfg.w_atr * atr_score)


def should_skip_trade(memories: list, hour_utc: int, trend_12h_pct: float,
                      regime: str, atr_h1: float, cfg: MemoryConfig) -> tuple[bool, str]:
    """Decision: skip this trade based on memory recall?

    Key insight: rank by PURE SIMILARITY (not outcome-weighted).
    We want the most contextually similar memories regardless of outcome,
    then check if those similar situations historically lost money.
    OWM's outcome weighting is for "recall useful patterns" — here we need
    "recall what happened in similar situations" which is outcome-agnostic.
    """
    scored = []
    for mem in memories:
        sim = context_similarity(mem, hour_utc, trend_12h_pct, regime, atr_h1, cfg)
        if sim >= cfg.similarity_cutoff:
            scored.append((mem, sim))  # pure similarity, no outcome bias

    scored.sort(key=lambda x: x[1], reverse=True)
    similar = scored[:cfg.top_k]

    if not similar:
        return False, "no_match"

    if cfg.skip_logic == "avg_negative":
        # Similarity-weighted average of outcomes
        total_w = sum(s for _, s in similar)
        if total_w == 0:
            return False, "zero_weight"
        weighted_pnl = sum(m.pnl_r * s for m, s in similar) / total_w
        if weighted_pnl < cfg.negative_threshold:
            return True, f"avg_r={weighted_pnl:.2f}"
        return False, f"avg_r={weighted_pnl:.2f}"

    elif cfg.skip_logic == "majority_negative":
        neg_count = sum(1 for m, _ in similar if m.pnl_r < 0)
        if neg_count > len(similar) / 2:
            return True, f"majority_neg={neg_count}/{len(similar)}"
        return False, f"majority_pos"

    return False, "unknown_logic"


def evaluate_with_memory(baseline_trades, test_contexts, test_atrs, memories,
                         cfg: MemoryConfig, atr_period: int):
    """Run memory filter on baseline trades, return metrics."""
    offset = atr_period + 1
    skipped_bars = set()
    skipped_winners = 0
    skipped_losers = 0

    for t in baseline_trades:
        ctx_idx = t.entry_bar
        if ctx_idx is not None and ctx_idx < len(test_contexts) and test_contexts[ctx_idx] is not None:
            ctx = test_contexts[ctx_idx]
            atr_val = test_atrs[ctx_idx] if ctx_idx < len(test_atrs) and test_atrs[ctx_idx] else 0

            skip, _ = should_skip_trade(
                memories, ctx.hour_utc, ctx.trend_12h_pct,
                str(ctx.regime.value) if hasattr(ctx.regime, 'value') else str(ctx.regime),
                atr_val, cfg
            )
            if skip:
                skipped_bars.add(t.entry_bar)
                if t.pnl > 0:
                    skipped_winners += 1
                else:
                    skipped_losers += 1

    kept = [t for t in baseline_trades if t.entry_bar not in skipped_bars]
    skipped_list = [t for t in baseline_trades if t.entry_bar in skipped_bars]
    skipped_pnl = sum(t.pnl for t in skipped_list)

    if not kept:
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0, len(skipped_list), skipped_pnl, skipped_winners, skipped_losers

    wins = [t for t in kept if t.pnl > 0]
    losses = [t for t in kept if t.pnl <= 0]
    total_pnl = sum(t.pnl for t in kept)
    win_rate = len(wins) / len(kept)
    gross_profit = sum(t.pnl for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.001
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    pnls = [t.pnl for t in kept]
    avg_pnl = sum(pnls) / len(pnls)
    std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)) ** 0.5
    sharpe = (avg_pnl / std_pnl * (252 * 24 / 6) ** 0.5) if std_pnl > 0 else 0

    cumulative = peak = max_dd = 0
    for t in kept:
        cumulative += t.pnl
        peak = max(peak, cumulative)
        dd = (peak - cumulative) / max(peak, 1) * 100
        max_dd = max(max_dd, dd)

    return (len(kept), win_rate, profit_factor, total_pnl, sharpe, max_dd,
            len(skipped_list), skipped_pnl, skipped_winners, skipped_losers)


# ── Agent: proposes next config based on history ────
class ResearchAgent:
    """Autonomous agent that proposes memory configurations.

    Like autoresearch: observes results -> decides what to try next.
    Starts with broad exploration, narrows to fine-tuning around best config.
    """

    def __init__(self):
        self.history: list[ExperimentResult] = []
        self.best_result: Optional[ExperimentResult] = None
        self.best_sharpe: float = -999
        self.phase = "explore"  # "explore" -> "exploit" -> "fine_tune"
        self.explore_count = 0

    def propose_next(self) -> MemoryConfig:
        """Agent decides what to try next based on history."""

        # Phase 1: Systematic exploration (first 8 iterations)
        if self.explore_count < 8:
            return self._explore()

        # Phase 2: Exploit — mutate the best config found so far
        if self.best_result and self.phase != "fine_tune":
            self.phase = "exploit"
            # After 5 exploit attempts without improvement, switch to fine-tune
            recent_improvements = sum(
                1 for r in self.history[-5:]
                if r.verdict == "KEEP"
            )
            if recent_improvements == 0 and len(self.history) > 13:
                self.phase = "fine_tune"
            return self._mutate_best()

        # Phase 3: Fine-tune — small perturbations around best
        if self.best_result:
            return self._fine_tune_best()

        # Fallback
        return MemoryConfig()

    def _explore(self) -> MemoryConfig:
        """Systematic exploration of the search space."""
        configs = [
            # 1. Default
            MemoryConfig(),
            # 2. Strict filter (high similarity required)
            MemoryConfig(similarity_cutoff=0.7, negative_threshold=-0.3, top_k=3),
            # 3. Loose filter (catch more patterns)
            MemoryConfig(similarity_cutoff=0.3, negative_threshold=-1.0, top_k=10),
            # 4. Hour-dominant (time-of-day matters most)
            MemoryConfig(w_hour=0.6, w_trend_dir=0.15, w_trend_mag=0.1, w_regime=0.1, w_atr=0.05),
            # 5. Regime-dominant (market regime matters most)
            MemoryConfig(w_hour=0.1, w_trend_dir=0.15, w_trend_mag=0.1, w_regime=0.55, w_atr=0.1),
            # 6. Majority vote instead of weighted average
            MemoryConfig(skip_logic="majority_negative", top_k=7),
            # 7. ATR-focused (volatility similarity matters most)
            MemoryConfig(w_hour=0.1, w_trend_dir=0.1, w_trend_mag=0.1, w_regime=0.1, w_atr=0.6),
            # 8. Combined: strict + majority
            MemoryConfig(similarity_cutoff=0.6, skip_logic="majority_negative",
                         negative_threshold=-0.3, top_k=5),
        ]
        idx = self.explore_count
        self.explore_count += 1
        return configs[idx]

    def _mutate_best(self) -> MemoryConfig:
        """Mutate the best config — one parameter at a time."""
        cfg = deepcopy(self.best_result.config)

        # Pick a random parameter to mutate
        param = random.choice(["similarity_cutoff", "negative_threshold", "top_k",
                                "w_hour", "w_trend_dir", "w_regime", "w_atr",
                                "skip_logic"])

        if param == "similarity_cutoff":
            cfg.similarity_cutoff = max(0.2, min(0.9, cfg.similarity_cutoff + random.uniform(-0.15, 0.15)))
        elif param == "negative_threshold":
            cfg.negative_threshold = max(-2.0, min(0.0, cfg.negative_threshold + random.uniform(-0.3, 0.3)))
        elif param == "top_k":
            cfg.top_k = max(1, min(20, cfg.top_k + random.randint(-3, 3)))
        elif param == "skip_logic":
            cfg.skip_logic = "majority_negative" if cfg.skip_logic == "avg_negative" else "avg_negative"
        else:
            # Weight mutation — adjust one weight, normalize others
            delta = random.uniform(-0.15, 0.15)
            old_val = getattr(cfg, param)
            new_val = max(0.05, min(0.8, old_val + delta))
            setattr(cfg, param, new_val)
            # Normalize weights to sum to ~1.0
            total = cfg.w_hour + cfg.w_trend_dir + cfg.w_trend_mag + cfg.w_regime + cfg.w_atr
            if total > 0:
                cfg.w_hour /= total
                cfg.w_trend_dir /= total
                cfg.w_trend_mag /= total
                cfg.w_regime /= total
                cfg.w_atr /= total

        return cfg

    def _fine_tune_best(self) -> MemoryConfig:
        """Small perturbations around best config."""
        cfg = deepcopy(self.best_result.config)
        cfg.similarity_cutoff += random.uniform(-0.05, 0.05)
        cfg.similarity_cutoff = max(0.2, min(0.9, cfg.similarity_cutoff))
        cfg.negative_threshold += random.uniform(-0.1, 0.1)
        cfg.negative_threshold = max(-2.0, min(0.0, cfg.negative_threshold))
        return cfg

    def evaluate(self, result: ExperimentResult):
        """Agent evaluates: keep or discard?"""
        self.history.append(result)
        if result.sharpe > self.best_sharpe:
            self.best_sharpe = result.sharpe
            self.best_result = result
            result.verdict = "KEEP"
            result.reason = f"new_best_sharpe={result.sharpe:.2f}"
        else:
            result.verdict = "DISCARD"
            result.reason = f"sharpe={result.sharpe:.2f}<best={self.best_sharpe:.2f}"


# ── Main experiment ─────────────────────────────────
async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    args = parser.parse_args()

    print("=" * 70)
    print("  AUTORESEARCH: Memory-Enhanced Trading")
    print("  Strategy E (Afternoon Engine) on BTCUSDT 1H")
    print(f"  Agent will run {args.iterations} autonomous iterations")
    print("=" * 70)

    ds = BinanceDataSource()
    strategy = build_strategy_e()

    try:
        # ── Step 1: Fetch data ──
        print(f"\n[DATA] Fetching training data: {TRAIN_START.date()} -> {TRAIN_END.date()}")
        train_data = await ds.fetch_ohlcv(SYMBOL, TIMEFRAME, TRAIN_START, TRAIN_END)
        print(f"  Training bars: {len(train_data.bars)}")

        print(f"[DATA] Fetching test data: {TEST_START.date()} -> {TEST_END.date()}")
        test_data = await ds.fetch_ohlcv(SYMBOL, TIMEFRAME, TEST_START, TEST_END)
        print(f"  Test bars: {len(test_data.bars)}")

        # ── Step 2: Precompute contexts + ATRs ──
        print("[PREP] Computing contexts and ATRs...")
        train_contexts = precompute_contexts(train_data, CONTEXT_CONFIG)
        train_atrs = precompute_atrs(train_data.bars, CONTEXT_CONFIG.atr_period)
        test_contexts = precompute_contexts(test_data, CONTEXT_CONFIG)
        test_atrs = precompute_atrs(test_data.bars, CONTEXT_CONFIG.atr_period)

        # ── Step 3: Generate memories from training period ──
        print("[TRAIN] Running baseline on training data...")
        train_fitness, train_trades = fast_backtest_with_trades(
            train_data.bars, train_contexts, train_atrs, strategy,
            config=CONTEXT_CONFIG, timeframe="1h"
        )
        print(f"  Training: {train_fitness.trade_count} trades | "
              f"WR: {train_fitness.win_rate:.1%} | Sharpe: {train_fitness.sharpe_ratio:.2f}")

        memories = []
        for t in train_trades:
            ctx = train_contexts[t.entry_bar] if t.entry_bar < len(train_contexts) else None
            atr_val = train_atrs[t.entry_bar] if t.entry_bar < len(train_atrs) else None
            if ctx is None or atr_val is None or atr_val <= 0:
                continue

            pnl_r = (t.exit_price - t.entry_price) / atr_val
            if t.direction == "short":
                pnl_r = -pnl_r

            memories.append(MemoryEntry(
                hour_utc=ctx.hour_utc,
                trend_12h_pct=ctx.trend_12h_pct or 0,
                regime=str(ctx.regime.value) if ctx.regime and hasattr(ctx.regime, 'value') else str(ctx.regime),
                atr_h1=atr_val,
                pnl_r=pnl_r,
            ))

        pos_mem = sum(1 for m in memories if m.pnl_r > 0)
        neg_mem = len(memories) - pos_mem
        print(f"  Memories: {len(memories)} (positive: {pos_mem}, negative: {neg_mem})")

        # ── Step 4: Baseline on test data ──
        print("\n[BASELINE] Running Strategy E unmodified on test data...")
        baseline_fitness, baseline_trades = fast_backtest_with_trades(
            test_data.bars, test_contexts, test_atrs, strategy,
            config=CONTEXT_CONFIG, timeframe="1h"
        )
        print(f"  Baseline: {baseline_fitness.trade_count} trades | "
              f"WR: {baseline_fitness.win_rate:.1%} | PF: {baseline_fitness.profit_factor:.2f} | "
              f"Sharpe: {baseline_fitness.sharpe_ratio:.2f} | PnL: ${baseline_fitness.total_pnl:.2f}")

        if not baseline_trades:
            print("\n  FAIL No baseline trades — nothing to filter. Experiment aborted.")
            return

        # ── Step 5: Autonomous agent loop ──
        print(f"\n{'='*70}")
        print(f"  AGENT LOOP: {args.iterations} iterations")
        print(f"{'='*70}")

        agent = ResearchAgent()
        journal = []

        for i in range(args.iterations):
            cfg = agent.propose_next()

            (n_kept, wr, pf, pnl, sharpe, dd,
             n_skipped, skip_pnl, skip_w, skip_l) = evaluate_with_memory(
                baseline_trades, test_contexts, test_atrs, memories,
                cfg, CONTEXT_CONFIG.atr_period
            )

            result = ExperimentResult(
                iteration=i + 1,
                config=cfg,
                trades=baseline_fitness.trade_count,
                kept_trades=n_kept,
                skipped=n_skipped,
                win_rate=wr,
                profit_factor=pf,
                total_pnl=pnl,
                sharpe=sharpe,
                max_dd_pct=dd,
                skipped_pnl=skip_pnl,
                skipped_winners=skip_w,
                skipped_losers=skip_l,
                verdict="",
                reason="",
            )

            agent.evaluate(result)

            # Log
            marker = "*" if result.verdict == "KEEP" else " "
            filter_quality = "+" if skip_l >= skip_w else "-"
            print(f"  [{i+1:2d}] {marker} Sharpe {sharpe:+6.2f} | "
                  f"PnL ${pnl:+8.2f} | WR {wr:.0%} | "
                  f"Skip {n_skipped}/{baseline_fitness.trade_count} "
                  f"({filter_quality} L{skip_l}/W{skip_w}) | "
                  f"{agent.phase} | {cfg.describe()}")

            journal.append({
                "iteration": i + 1,
                "phase": agent.phase,
                "config": asdict(cfg),
                "sharpe": round(sharpe, 4),
                "pnl": round(pnl, 2),
                "win_rate": round(wr, 4),
                "profit_factor": round(pf, 4),
                "skipped": n_skipped,
                "skipped_pnl": round(skip_pnl, 2),
                "skipped_winners": skip_w,
                "skipped_losers": skip_l,
                "verdict": result.verdict,
                "reason": result.reason,
            })

        # ── Summary ──
        print(f"\n{'='*70}")
        print(f"  RESEARCH SUMMARY")
        print(f"{'='*70}")

        print(f"\n  Baseline (no memory):")
        print(f"    Trades: {baseline_fitness.trade_count} | WR: {baseline_fitness.win_rate:.1%} | "
              f"PF: {baseline_fitness.profit_factor:.2f} | Sharpe: {baseline_fitness.sharpe_ratio:.2f} | "
              f"PnL: ${baseline_fitness.total_pnl:.2f}")

        if agent.best_result:
            b = agent.best_result
            print(f"\n  Best memory config (iter {b.iteration}):")
            print(f"    Trades: {b.kept_trades} | WR: {b.win_rate:.1%} | "
                  f"PF: {b.profit_factor:.2f} | Sharpe: {b.sharpe:.2f} | "
                  f"PnL: ${b.total_pnl:.2f}")
            print(f"    Skipped: {b.skipped} trades (PnL ${b.skipped_pnl:+.2f}, "
                  f"L{b.skipped_losers}/W{b.skipped_winners})")
            print(f"    Config: {b.config.describe()}")

            sharpe_delta = b.sharpe - baseline_fitness.sharpe_ratio
            pnl_delta = b.total_pnl - baseline_fitness.total_pnl
            wr_delta = b.win_rate - baseline_fitness.win_rate

            print(f"\n  Delta vs baseline:")
            print(f"    Sharpe: {sharpe_delta:+.2f}")
            print(f"    PnL:    ${pnl_delta:+.2f}")
            print(f"    WR:     {wr_delta*100:+.1f}pp")

            if sharpe_delta >= 0.5 and wr_delta >= -0.05 and b.skipped_losers > b.skipped_winners:
                print(f"\n  PASS HYPOTHESIS VALIDATED: Memory injection improves trading")
            elif sharpe_delta > 0:
                print(f"\n  ~ PARTIAL: Memory helps (Sharpe +{sharpe_delta:.2f}) but below threshold")
            else:
                print(f"\n  FAIL HYPOTHESIS REJECTED: Memory injection does not improve Sharpe")

            if b.skipped_losers > b.skipped_winners:
                print(f"  PASS Filter quality: correctly skips more losers than winners")
            else:
                print(f"  FAIL Filter quality: skips too many winners")

        # Agent learning summary
        keeps = sum(1 for r in agent.history if r.verdict == "KEEP")
        print(f"\n  Agent stats: {keeps} improvements found in {len(agent.history)} iterations")
        print(f"  Phases: explore({agent.explore_count}) -> {agent.phase}")

        # ── Save research journal ──
        output_path = Path(__file__).parent / "output" / "memory_autoresearch.json"
        output_path.parent.mkdir(exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "experiment": "memory_autoresearch",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "program": "scripts/research/program.md",
                "symbol": SYMBOL,
                "strategy": "Strategy E (Afternoon Engine)",
                "train_period": f"{TRAIN_START.date()} to {TRAIN_END.date()}",
                "test_period": f"{TEST_START.date()} to {TEST_END.date()}",
                "memories_count": len(memories),
                "baseline": {
                    "trades": baseline_fitness.trade_count,
                    "win_rate": round(baseline_fitness.win_rate, 4),
                    "profit_factor": round(baseline_fitness.profit_factor, 4),
                    "total_pnl": round(baseline_fitness.total_pnl, 2),
                    "sharpe": round(baseline_fitness.sharpe_ratio, 2),
                    "max_dd_pct": round(baseline_fitness.max_drawdown_pct, 2),
                },
                "best_config": asdict(agent.best_result.config) if agent.best_result else None,
                "best_sharpe": round(agent.best_sharpe, 4),
                "journal": journal,
            }, f, indent=2, ensure_ascii=False)
        print(f"\n  Journal saved: {output_path}")

    finally:
        await ds.close()


if __name__ == "__main__":
    asyncio.run(main())

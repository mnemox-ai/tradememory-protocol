#!/usr/bin/env python3
"""Phase 13 Step 1: Random Baseline Validation with Real Binance Data.

Fetches BTCUSDT 1H data (June 2024 - March 2026), generates 1000 random
strategies, backtests each, then ranks Strategy C and Strategy E against
the random distribution.

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/run_real_baseline.py
"""

import asyncio
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.context_builder import ContextConfig, MarketContext, build_context, compute_atr
from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.backtester import (
    Position,
    Trade,
    _compute_fitness,
    backtest,
    check_entry,
    check_exit_position,
    force_close_position,
    open_position,
)
from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    EntryCondition,
    ExitCondition,
    FitnessMetrics,
    RuleCondition,
    ValidityConditions,
)
from tradememory.evolution.random_baseline import (
    BaselineResult,
    RandomStrategyGenerator,
    compute_percentile_rank,
    rank_strategies,
    run_baseline,
)


def precompute_contexts(series: OHLCVSeries, config: Optional[ContextConfig] = None):
    """Precompute MarketContext for every bar in the series.

    Returns a list of contexts (same length as series.bars), where
    contexts[i] is None for bars before min_bar (not enough history).
    """
    cfg = config or ContextConfig()
    n = len(series.bars)
    min_bar = cfg.atr_period + 1
    contexts = [None] * n
    for i in range(min_bar, n):
        if i % 500 == 0:
            print(f"    context {i}/{n}...", flush=True)
        contexts[i] = build_context(series, bar_index=i, config=cfg)
    return contexts


def precompute_atrs(bars: List[OHLCV], atr_period: int = 14):
    """Precompute ATR for every bar in the series.

    Returns a list of ATR values (same length as bars), where
    atrs[i] is None for bars before atr_period + 1.
    """
    n = len(bars)
    atrs = [None] * n
    for i in range(atr_period + 1, n):
        atrs[i] = compute_atr(bars[max(0, i - atr_period - 1): i + 1], atr_period)
    return atrs


def fast_backtest(
    bars: List[OHLCV],
    contexts: list,
    atrs: list,
    pattern: CandidatePattern,
    config: Optional[ContextConfig] = None,
    timeframe: str = "1h",
) -> FitnessMetrics:
    """Backtest using precomputed contexts and ATRs (avoids redundant computation)."""
    if not bars or len(bars) < 30:
        return FitnessMetrics()
    cfg = config or ContextConfig()
    min_bar = cfg.atr_period + 1
    trades: List[Trade] = []
    position: Optional[Position] = None

    for i in range(min_bar, len(bars)):
        current_bar = bars[i]
        ctx = contexts[i]

        if position is not None:
            trade = check_exit_position(position, current_bar, i)
            if trade is not None:
                trades.append(trade)
                position = None

        if position is None and ctx is not None:
            if check_entry(pattern, ctx):
                atr = atrs[i]
                if atr is None or atr <= 0:
                    continue
                position = open_position(pattern, current_bar, i, atr)

    if position is not None:
        last_bar = bars[-1]
        trade = force_close_position(position, last_bar, len(bars) - 1, "end")
        trades.append(trade)

    return _compute_fitness(trades, timeframe=timeframe)


def fast_run_baseline(
    bars: List[OHLCV],
    contexts: list,
    atrs: list,
    n_strategies: int = 1000,
    seed: int = 42,
    timeframe: str = "1h",
) -> BaselineResult:
    """Run random baseline using precomputed contexts and ATRs."""
    gen = RandomStrategyGenerator(seed=seed)
    candidates = gen.generate(n_strategies)
    sharpes = []
    for idx, pattern in enumerate(candidates):
        if idx % 100 == 0:
            print(f"    strategy {idx}/{n_strategies}...", flush=True)
        metrics = fast_backtest(bars, contexts, atrs, pattern, timeframe=timeframe)
        sharpes.append(metrics.sharpe_ratio)
    sharpes.sort()
    n = len(sharpes)
    mean_s = sum(sharpes) / n if n > 0 else 0
    var_s = sum((s - mean_s) ** 2 for s in sharpes) / (n - 1) if n > 1 else 0
    std_s = math.sqrt(var_s) if var_s > 0 else 0
    p95 = sharpes[int(n * 0.95)] if n > 0 else 0
    return BaselineResult(
        n_strategies=n_strategies,
        sharpe_distribution=sharpes,
        mean_sharpe=round(mean_s, 4),
        std_sharpe=round(std_s, 4),
        percentile_95=round(p95, 4),
        seed=seed,
    )


def build_strategy_c() -> CandidatePattern:
    """Strategy C: US Session Drain — SHORT at 16:00 UTC when 12h trend DOWN."""
    return CandidatePattern(
        pattern_id="STRAT-C",
        name="Strategy C (US Session Drain)",
        description="SHORT at 16:00 UTC when 12h trend is negative",
        entry_condition=EntryCondition(
            direction="short",
            conditions=[
                RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=16),
                RuleCondition(field="trend_12h_pct", op=ConditionOperator.LT, value=0),
            ],
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=1.0,
            take_profit_atr=2.0,
            max_holding_bars=6,
        ),
        confidence=0.8,
        source="evolution_engine",
    )


from strategy_definitions import build_strategy_e  # noqa: E402


def build_strategy_c_notrend() -> CandidatePattern:
    """Strategy C without trend filter — only hour_utc=16, short."""
    return CandidatePattern(
        pattern_id="STRAT-C-NOTREND",
        name="Strategy C (no trend filter)",
        description="SHORT at 16:00 UTC, no trend filter",
        entry_condition=EntryCondition(
            direction="short",
            conditions=[
                RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=16),
            ],
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=1.0,
            take_profit_atr=2.0,
            max_holding_bars=6,
        ),
        confidence=0.5,
        source="ablation",
    )


def build_strategy_e_notrend() -> CandidatePattern:
    """Strategy E without trend filter — only hour_utc=14, long."""
    return CandidatePattern(
        pattern_id="STRAT-E-NOTREND",
        name="Strategy E (no trend filter)",
        description="LONG at 14:00 UTC, no trend filter",
        entry_condition=EntryCondition(
            direction="long",
            conditions=[
                RuleCondition(field="hour_utc", op=ConditionOperator.EQ, value=14),
            ],
        ),
        exit_condition=ExitCondition(
            stop_loss_atr=1.0,
            take_profit_atr=2.0,
            max_holding_bars=6,
        ),
        confidence=0.5,
        source="ablation",
    )


async def main():
    print("=" * 70)
    print("Phase 13 Step 1: Random Baseline Validation (OPTIMIZED)")
    print("=" * 70)

    # --- Step 1: Fetch data ---
    print("\n[1/5] Fetching BTCUSDT 1H data from Binance...")
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

    # --- Step 3: Run 1000 random strategies ---
    print("\n[3/5] Running 1000 random strategies...")
    t1 = time.time()
    result = fast_run_baseline(bars, contexts, atrs, n_strategies=1000, seed=42, timeframe="1h")
    baseline_time = time.time() - t1
    print(f"  Done in {baseline_time:.1f}s")
    print(f"  Mean Sharpe: {result.mean_sharpe:.4f}")
    print(f"  Std Sharpe:  {result.std_sharpe:.4f}")

    # Distribution percentiles
    dist = result.sharpe_distribution
    p5 = dist[int(len(dist) * 0.05)] if dist else 0
    p25 = dist[int(len(dist) * 0.25)] if dist else 0
    p50 = dist[int(len(dist) * 0.50)] if dist else 0
    p75 = dist[int(len(dist) * 0.75)] if dist else 0
    p95 = result.percentile_95
    print(f"\n  Distribution:")
    print(f"    P5:  {p5:.4f}")
    print(f"    P25: {p25:.4f}")
    print(f"    P50: {p50:.4f}")
    print(f"    P75: {p75:.4f}")
    print(f"    P95: {p95:.4f}")
    print(f"    Min: {dist[0]:.4f}" if dist else "    Min: N/A")
    print(f"    Max: {dist[-1]:.4f}" if dist else "    Max: N/A")

    # --- Step 4: Backtest Strategy C and E ---
    print("\n[4/5] Backtesting Strategy C, E, and ablations...")

    strategies = {
        "Strategy C (full)": build_strategy_c(),
        "Strategy E (full)": build_strategy_e(),
        "Strategy C (no trend)": build_strategy_c_notrend(),
        "Strategy E (no trend)": build_strategy_e_notrend(),
    }

    strategy_results = {}
    for name, pattern in strategies.items():
        metrics = fast_backtest(bars, contexts, atrs, pattern, timeframe="1h")
        strategy_results[name] = {
            "sharpe": metrics.sharpe_ratio,
            "trades": metrics.trade_count,
            "win_rate": metrics.win_rate,
            "pf": metrics.profit_factor,
            "total_pnl": metrics.total_pnl,
            "max_dd": metrics.max_drawdown_pct,
            "avg_hold": metrics.avg_holding_bars,
        }
        print(f"  {name}: Sharpe={metrics.sharpe_ratio:.4f}, "
              f"trades={metrics.trade_count}, WR={metrics.win_rate:.1%}, "
              f"PF={metrics.profit_factor:.2f}")

    # --- Step 5: Rank against baseline ---
    print("\n[5/5] Ranking against random baseline...")
    sharpe_map = {name: r["sharpe"] for name, r in strategy_results.items()}
    rankings = rank_strategies(sharpe_map, result)

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"\nBaseline: 1000 random strategies on BTCUSDT 1H")
    print(f"Period: {start_dt.date()} -> {end_dt.date()} ({series.count} bars)")
    print(f"Random distribution: mean={result.mean_sharpe:.4f}, "
          f"std={result.std_sharpe:.4f}, P95={p95:.4f}")
    print(f"Timing: precompute={precompute_time:.0f}s, "
          f"1000 backtests={baseline_time:.0f}s, "
          f"total={precompute_time + baseline_time:.0f}s")

    print(f"\n{'Strategy':<30} {'Sharpe':>8} {'Pctile':>8} {'Trades':>8} "
          f"{'WR':>8} {'Pass?':>8}")
    print("-" * 70)
    for name, rank in rankings.items():
        r = strategy_results[name]
        status = "PASS" if rank["passes_5pct"] else "FAIL"
        print(f"{name:<30} {rank['sharpe']:>8.4f} {rank['percentile']:>7.1f}% "
              f"{r['trades']:>8d} {r['win_rate']:>7.1%} {status:>8}")

    # Verdict
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    c_pass = rankings.get("Strategy C (full)", {}).get("passes_5pct", False)
    e_pass = rankings.get("Strategy E (full)", {}).get("passes_5pct", False)

    if c_pass and e_pass:
        print("Both Strategy C and E beat the 95th percentile of random.")
        print("→ Proceed to Step 2 (Walk-Forward)")
    elif c_pass or e_pass:
        passed = "C" if c_pass else "E"
        failed = "E" if c_pass else "C"
        print(f"Strategy {passed} passes, Strategy {failed} does NOT.")
        print(f"→ Investigate Strategy {failed} (Step 1B diagnosis)")
    else:
        print("Neither Strategy C nor E beats the random baseline.")
        print("→ Go to Step 1B: check if RR structure alone explains results")

    # Ablation analysis
    print("\nAblation (trend filter contribution):")
    for base in ["C", "E"]:
        full_key = f"Strategy {base} (full)"
        notrend_key = f"Strategy {base} (no trend)"
        if full_key in rankings and notrend_key in rankings:
            full_pct = rankings[full_key]["percentile"]
            notrend_pct = rankings[notrend_key]["percentile"]
            delta = full_pct - notrend_pct
            print(f"  Strategy {base}: full={full_pct:.1f}% vs no-trend={notrend_pct:.1f}% "
                  f"(trend filter adds {delta:+.1f} percentile points)")

    # Save results to JSON for VALIDATION_RESULTS.md update
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_period": f"{start_dt.date()} to {end_dt.date()}",
        "bars": series.count,
        "n_random": 1000,
        "seed": 42,
        "baseline": {
            "mean_sharpe": result.mean_sharpe,
            "std_sharpe": result.std_sharpe,
            "p5": round(p5, 4),
            "p25": round(p25, 4),
            "p50": round(p50, 4),
            "p75": round(p75, 4),
            "p95": round(p95, 4),
        },
        "strategies": {
            name: {**strategy_results[name], **rankings[name]}
            for name in rankings
        },
    }
    out_path = Path(__file__).parent.parent / "validation_step1_results.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

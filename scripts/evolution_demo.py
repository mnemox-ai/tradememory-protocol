#!/usr/bin/env python3
"""Evolution Engine E2E Demo — standalone, no API keys needed.

Generates mock BTC 1H OHLCV data (500 bars with realistic price action),
runs 3 generations of evolution with MockLLMClient, and prints results.

Usage:
    python scripts/evolution_demo.py
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import List

from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.engine import EngineConfig, EvolutionEngine
from tradememory.evolution.llm import MockLLMClient
from tradememory.evolution.models import EvolutionConfig, FitnessMetrics, Hypothesis


# --- Mock OHLCV Data Generator ---


def generate_mock_btc_1h(
    bars: int = 500,
    start_price: float = 65000.0,
    seed: int = 42,
) -> OHLCVSeries:
    """Generate realistic BTC 1H OHLCV data using geometric Brownian motion.

    Features:
    - Mean-reverting volatility (high-vol periods cluster, then calm down)
    - Session-based volume profile (higher during US hours)
    - Slight upward drift (0.01% per bar ≈ ~60% annualized)
    """
    rng = random.Random(seed)
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = start_price
    base_vol = 0.004  # ~0.4% per hour base volatility
    vol = base_vol
    ohlcv_bars: List[OHLCV] = []

    for i in range(bars):
        ts = start_dt + timedelta(hours=i)
        hour = ts.hour

        # Mean-reverting volatility
        vol = vol + 0.1 * (base_vol - vol) + 0.001 * rng.gauss(0, 1)
        vol = max(0.001, min(0.015, vol))

        # Slight upward drift
        drift = 0.0001
        ret = drift + vol * rng.gauss(0, 1)
        close = price * (1 + ret)

        # Intra-bar high/low from volatility
        intra_vol = abs(vol * rng.gauss(0, 1.5))
        high = max(price, close) * (1 + intra_vol)
        low = min(price, close) * (1 - intra_vol)

        # Volume: higher during US session (14-21 UTC)
        base_volume = 100 + rng.random() * 200
        if 14 <= hour <= 21:
            base_volume *= 2.5
        elif 8 <= hour <= 13:
            base_volume *= 1.5

        ohlcv_bars.append(OHLCV(
            timestamp=ts,
            open=round(price, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            volume=round(base_volume, 2),
        ))
        price = close

    return OHLCVSeries(
        symbol="BTCUSDT",
        timeframe=Timeframe.H1,
        bars=ohlcv_bars,
        source="mock_generator",
    )


# --- Mock LLM Responses (3 patterns each) ---


def _make_pattern(
    name: str,
    description: str,
    direction: str,
    conditions: list,
    sl_atr: float,
    tp_atr: float,
    max_bars: int,
    confidence: float = 0.7,
) -> dict:
    return {
        "name": name,
        "description": description,
        "entry_condition": {
            "direction": direction,
            "conditions": conditions,
            "description": description,
        },
        "exit_condition": {
            "stop_loss_atr": sl_atr,
            "take_profit_atr": tp_atr,
            "max_holding_bars": max_bars,
        },
        "confidence": confidence,
        "sample_count": 50,
    }


# Generation 0: pure exploration — 3 diverse patterns
GEN0_RESPONSE = json.dumps({"patterns": [
    _make_pattern(
        "US Session Momentum",
        "Long when US session opens with positive 12H trend",
        "long",
        [
            {"field": "hour_utc", "op": "eq", "value": 14},
            {"field": "trend_12h_pct", "op": "gt", "value": 0},
        ],
        sl_atr=1.5, tp_atr=3.0, max_bars=8, confidence=0.7,
    ),
    _make_pattern(
        "Overnight Mean Reversion",
        "Short during low-vol Asian session when overbought",
        "short",
        [
            {"field": "hour_utc", "op": "eq", "value": 3},
            {"field": "trend_12h_pct", "op": "gt", "value": 1.0},
        ],
        sl_atr=2.0, tp_atr=2.5, max_bars=12, confidence=0.6,
    ),
    _make_pattern(
        "Volatility Breakout",
        "Long when volatility expands in European session",
        "long",
        [
            {"field": "hour_utc", "op": "eq", "value": 9},
            {"field": "atr_percentile", "op": "gt", "value": 70},
        ],
        sl_atr=1.2, tp_atr=4.0, max_bars=6, confidence=0.65,
    ),
]})

# Generation 1: mutations of gen0 survivors + new exploration
GEN1_RESPONSE_EXPLORE = json.dumps({"patterns": [
    _make_pattern(
        "London Afternoon Drift",
        "Long at 15:00 UTC riding afternoon momentum",
        "long",
        [
            {"field": "hour_utc", "op": "eq", "value": 15},
            {"field": "trend_12h_pct", "op": "gt", "value": 0.3},
        ],
        sl_atr=1.8, tp_atr=3.5, max_bars=10, confidence=0.65,
    ),
    _make_pattern(
        "Asian Dip Buy",
        "Long during Asian low when trend is up",
        "long",
        [
            {"field": "hour_utc", "op": "eq", "value": 2},
            {"field": "trend_12h_pct", "op": "gt", "value": 0.5},
        ],
        sl_atr=1.5, tp_atr=2.0, max_bars=8, confidence=0.55,
    ),
    _make_pattern(
        "Tight Range Breakout",
        "Long when low ATR transitions to normal",
        "long",
        [
            {"field": "hour_utc", "op": "eq", "value": 10},
            {"field": "atr_percentile", "op": "lt", "value": 30},
        ],
        sl_atr=1.0, tp_atr=5.0, max_bars=12, confidence=0.6,
    ),
]})

# Mutation response (reused for gen1 and gen2 mutations)
MUTATION_RESPONSE = json.dumps({"patterns": [
    _make_pattern(
        "US Momentum v2",
        "Tighter stops on US momentum with hour flexibility",
        "long",
        [
            {"field": "hour_utc", "op": "eq", "value": 14},
            {"field": "trend_12h_pct", "op": "gt", "value": 0.2},
        ],
        sl_atr=1.2, tp_atr=3.5, max_bars=6, confidence=0.75,
    ),
]})

# Generation 2: more exploration + mutations
GEN2_RESPONSE_EXPLORE = json.dumps({"patterns": [
    _make_pattern(
        "NY Close Reversal",
        "Short at NY close when overextended",
        "short",
        [
            {"field": "hour_utc", "op": "eq", "value": 21},
            {"field": "trend_12h_pct", "op": "gt", "value": 1.5},
        ],
        sl_atr=1.5, tp_atr=2.5, max_bars=8, confidence=0.6,
    ),
    _make_pattern(
        "Early Bird EU",
        "Long at EU open with overnight momentum",
        "long",
        [
            {"field": "hour_utc", "op": "eq", "value": 7},
            {"field": "trend_12h_pct", "op": "gt", "value": 0},
        ],
        sl_atr=1.3, tp_atr=3.0, max_bars=10, confidence=0.7,
    ),
    _make_pattern(
        "Late Night Scalp",
        "Quick long during quiet hours",
        "long",
        [
            {"field": "hour_utc", "op": "eq", "value": 0},
            {"field": "trend_12h_pct", "op": "gt", "value": 0},
        ],
        sl_atr=0.8, tp_atr=1.5, max_bars=4, confidence=0.5,
    ),
]})


def build_mock_responses() -> list[str]:
    """Build the sequence of mock LLM responses for 3 generations.

    Gen 0: 1 discovery call → GEN0_RESPONSE
    Gen 1: 1 exploration + N mutation calls
    Gen 2: 1 exploration + N mutation calls
    Provide enough responses for the engine's calls.
    """
    responses = [
        GEN0_RESPONSE,           # Gen 0: discovery
        GEN1_RESPONSE_EXPLORE,   # Gen 1: exploration
        MUTATION_RESPONSE,       # Gen 1: mutation of graduated[0]
        MUTATION_RESPONSE,       # Gen 1: mutation of graduated[1] (if any)
        MUTATION_RESPONSE,       # Gen 1: extra mutation
        GEN2_RESPONSE_EXPLORE,   # Gen 2: exploration
        MUTATION_RESPONSE,       # Gen 2: mutation
        MUTATION_RESPONSE,       # Gen 2: mutation
        MUTATION_RESPONSE,       # Gen 2: extra
        MUTATION_RESPONSE,       # spare
    ]
    return responses


# --- Output Formatting ---


def print_header(text: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


def print_hypothesis(h: Hypothesis, rank: int) -> None:
    f = h.fitness_oos or h.fitness_is
    if f is None:
        return
    print(f"\n  #{rank} {h.pattern.name} (gen {h.generation})")
    print(f"     Status: {h.status.value}")
    print(f"     Direction: {h.pattern.entry_condition.direction}")
    print(f"     Conditions: {len(h.pattern.entry_condition.conditions)}")
    print(f"     SL: {h.pattern.exit_condition.stop_loss_atr}x ATR  "
          f"TP: {h.pattern.exit_condition.take_profit_atr}x ATR  "
          f"Max bars: {h.pattern.exit_condition.max_holding_bars}")
    print(f"     Trades: {f.trade_count}  Win rate: {f.win_rate:.1%}  "
          f"PF: {f.profit_factor:.2f}")
    print(f"     Sharpe: {f.sharpe_ratio:.2f}  "
          f"PnL: ${f.total_pnl:,.2f}  "
          f"Max DD: {f.max_drawdown_pct:.1f}%")


def print_equity_curve(hypotheses: List[Hypothesis]) -> None:
    """Print a simple text equity curve for the best hypothesis."""
    # Find hypothesis with best total PnL from IS
    best = None
    best_pnl = float("-inf")
    for h in hypotheses:
        f = h.fitness_is
        if f and f.total_pnl > best_pnl:
            best_pnl = f.total_pnl
            best = h

    if best is None or best.fitness_is is None:
        print("\n  (no trades to plot)")
        return

    f = best.fitness_is
    print(f"\n  Best IS strategy: {best.pattern.name}")
    print(f"  Trades: {f.trade_count} | PnL: ${f.total_pnl:,.2f} | "
          f"Sharpe: {f.sharpe_ratio:.2f}")

    # Simulate equity curve from fitness
    # We don't have individual trades, so create a synthetic curve
    n_points = min(f.trade_count, 20)
    if n_points <= 0:
        print("  (no trades)")
        return

    avg_pnl = f.total_pnl / f.trade_count
    std_pnl = abs(avg_pnl) * 1.5  # approximate

    rng = random.Random(123)
    equity = 0.0
    points = [0.0]
    for _ in range(n_points):
        # Approximate trade PnL distribution
        if rng.random() < f.win_rate:
            trade_pnl = abs(avg_pnl) * (1 + rng.gauss(0, 0.3))
        else:
            trade_pnl = -abs(avg_pnl) * 0.7 * (1 + rng.gauss(0, 0.3))
        equity += trade_pnl
        points.append(equity)

    # Normalize to chart width
    width = 50
    min_eq = min(points)
    max_eq = max(points)
    span = max_eq - min_eq if max_eq != min_eq else 1

    print()
    print("  Equity Curve (approximate):")
    print(f"  {'':>4} {'$' + f'{min_eq:,.0f}':>10} {'':>{width // 2 - 5}}{'$' + f'{max_eq:,.0f}':>{width // 2}}")
    print(f"  {'':>4} |{'─' * width}|")

    for i, eq in enumerate(points):
        pos = int((eq - min_eq) / span * width)
        bar = " " * pos + "█"
        label = f"T{i:>2}"
        print(f"  {label} |{bar:<{width}}|")

    print(f"  {'':>4} |{'─' * width}|")


def print_graveyard_summary(graveyard: List[Hypothesis]) -> None:
    if not graveyard:
        print("\n  (empty graveyard)")
        return

    print(f"\n  {len(graveyard)} strategies eliminated:")
    for h in graveyard[:8]:
        reason = h.elimination_reason or "unknown"
        print(f"    ✗ {h.pattern.name} (gen {h.generation}) — {reason}")
    if len(graveyard) > 8:
        print(f"    ... and {len(graveyard) - 8} more")


# --- Main Demo ---


async def run_demo(seed: int = 42) -> dict:
    """Run the evolution demo. Returns summary dict for testing."""

    print_header("Evolution Engine Demo — BTC 1H Mock Data")

    # Step 1: Generate mock data
    print("\n[1/3] Generating 500 bars of mock BTC 1H data...")
    series = generate_mock_btc_1h(bars=500, seed=seed)
    print(f"  Symbol: {series.symbol}")
    print(f"  Period: {series.start} → {series.end}")
    print(f"  Bars: {series.count}")
    closes = [b.close for b in series.bars]
    print(f"  Price range: ${min(closes):,.2f} — ${max(closes):,.2f}")

    # Step 2: Configure and run evolution
    print("\n[2/3] Running 3 generations of evolution...")
    mock_llm = MockLLMClient(responses=build_mock_responses())

    config = EngineConfig(
        evolution=EvolutionConfig(
            symbol="BTCUSDT",
            timeframe="1h",
            generations=3,
            population_size=3,  # small for demo speed
            is_oos_ratio=0.7,
        ),
    )
    # Relax selection thresholds for demo (mock data won't produce 30+ trades)
    config.selection.min_is_trade_count = 1
    config.selection.min_oos_trade_count = 1
    config.selection.min_oos_sharpe = -999  # accept anything for demo
    config.selection.min_oos_profit_factor = 0
    config.selection.min_oos_win_rate = 0

    engine = EvolutionEngine(mock_llm, config)
    run = await engine.evolve(series)

    # Step 3: Print results
    print_header("Results")

    summary = run.summary
    print(f"\n  Run ID: {summary['run_id']}")
    print(f"  Generations: {summary['generations']}")
    print(f"  Total hypotheses tested: {summary['total_hypotheses']}")
    print(f"  Total backtests: {summary['total_backtests']}")
    print(f"  LLM tokens used: {summary['total_llm_tokens']}")
    print(f"  Graduated: {summary['graduated']}")
    print(f"  Eliminated: {summary['eliminated']}")

    # Surviving strategies
    print_header("Surviving Strategies")
    if run.graduated:
        for i, h in enumerate(run.graduated, 1):
            print_hypothesis(h, i)
    else:
        print("\n  No strategies graduated (common with mock data — ")
        print("  real LLM patterns would be more targeted)")

    # All hypotheses sorted by IS Sharpe
    print_header("All Hypotheses (by IS Sharpe)")
    sorted_hyps = sorted(
        [h for h in run.hypotheses if h.fitness_is],
        key=lambda h: h.fitness_is.sharpe_ratio,
        reverse=True,
    )
    for i, h in enumerate(sorted_hyps[:10], 1):
        print_hypothesis(h, i)

    # Equity curve
    print_header("Equity Curve")
    print_equity_curve(run.hypotheses)

    # Graveyard
    print_header("Strategy Graveyard")
    print_graveyard_summary(run.graveyard)

    print_header("Demo Complete")
    print(f"\n  The evolution engine tested {summary['total_hypotheses']} strategies")
    print(f"  across {summary['generations']} generations with {summary['total_backtests']} backtests.")
    print("  In production, use AnthropicClient for real LLM-powered discovery.")
    print()

    return summary


def main():
    summary = asyncio.run(run_demo())
    return summary


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Evolution Engine LIVE test — real Anthropic API.

Uses claude-haiku-4-5-20251001 for cost-effective pipeline validation.
Generates mock BTC 1H data, runs N generations with real LLM discovery.

Usage:
    python scripts/research/evolution_live_test.py
    python scripts/research/evolution_live_test.py --rounds 3 --pop 5

Requires ANTHROPIC_API_KEY in .env or environment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

# Load .env before imports that need the key
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            k, v = key.strip(), value.strip()
            if v:  # only set if value is non-empty
                os.environ[k] = v

from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.engine import EngineConfig, EvolutionEngine
from tradememory.evolution.llm import AnthropicClient, LLMError
from tradememory.evolution.models import (
    EvolutionConfig,
    Hypothesis,
    HypothesisStatus,
)
from tradememory.evolution.selector import SelectionConfig

# Configure logging — show LLM interactions
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("evolution_live")

# Quiet down noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)


# --- Mock Data (same as evolution_demo.py) ---


def generate_mock_btc_1h(
    bars: int = 500,
    start_price: float = 65000.0,
    seed: int = 42,
) -> OHLCVSeries:
    """Generate realistic BTC 1H OHLCV data."""
    rng = random.Random(seed)
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = start_price
    base_vol = 0.004
    vol = base_vol
    ohlcv_bars: List[OHLCV] = []

    for i in range(bars):
        ts = start_dt + timedelta(hours=i)
        hour = ts.hour
        vol = vol + 0.1 * (base_vol - vol) + 0.001 * rng.gauss(0, 1)
        vol = max(0.001, min(0.015, vol))
        drift = 0.0001
        ret = drift + vol * rng.gauss(0, 1)
        close = price * (1 + ret)
        intra_vol = abs(vol * rng.gauss(0, 1.5))
        high = max(price, close) * (1 + intra_vol)
        low = min(price, close) * (1 - intra_vol)
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


# --- Output Formatting ---

W = 70


def header(text: str) -> None:
    print(f"\n{'=' * W}")
    print(f"  {text}")
    print(f"{'=' * W}")


def print_hypothesis(h: Hypothesis, rank: int) -> None:
    f = h.fitness_oos or h.fitness_is
    if f is None:
        return
    status_mark = {
        HypothesisStatus.GRADUATED: "[PASS]",
        HypothesisStatus.ELIMINATED: "[FAIL]",
        HypothesisStatus.SURVIVED_IS: "[IS-OK]",
        HypothesisStatus.SURVIVED_OOS: "[OOS-OK]",
    }.get(h.status, "[?]")

    print(f"\n  {status_mark} #{rank} {h.pattern.name} (gen {h.generation})")
    print(f"     {h.pattern.description[:80]}")
    print(f"     Direction: {h.pattern.entry_condition.direction} | "
          f"Conditions: {len(h.pattern.entry_condition.conditions)}")
    entry_desc = ", ".join(
        f"{c.field} {c.op} {c.value}"
        for c in h.pattern.entry_condition.conditions
    )
    print(f"     Entry: {entry_desc[:70]}")
    print(f"     SL: {h.pattern.exit_condition.stop_loss_atr}x ATR  "
          f"TP: {h.pattern.exit_condition.take_profit_atr}x ATR  "
          f"Max: {h.pattern.exit_condition.max_holding_bars} bars")
    print(f"     Trades: {f.trade_count}  Win: {f.win_rate:.1%}  "
          f"PF: {f.profit_factor:.2f}  Sharpe: {f.sharpe_ratio:.2f}")
    print(f"     PnL: ${f.total_pnl:,.2f}  Max DD: {f.max_drawdown_pct:.1f}%")
    if h.elimination_reason:
        print(f"     Reason: {h.elimination_reason}")


# --- Main ---


async def run_live_test(
    rounds: int = 2,
    population: int = 3,
    model: str = "claude-haiku-4-5-20251001",
    bars: int = 500,
) -> dict:
    """Run evolution with real Anthropic API."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in environment or .env")
        sys.exit(1)

    header(f"Evolution Engine LIVE Test — {model}")
    print(f"\n  Model: {model}")
    print(f"  Rounds: {rounds}")
    print(f"  Population: {population}/round")
    print(f"  Data: {bars} bars mock BTC 1H")

    # Step 1: Generate data
    header("Step 1: Generate Mock Data")
    series = generate_mock_btc_1h(bars=bars)
    closes = [b.close for b in series.bars]
    print(f"  Symbol: {series.symbol}")
    print(f"  Period: {series.start} -> {series.end}")
    print(f"  Bars: {series.count}")
    print(f"  Price: ${min(closes):,.2f} - ${max(closes):,.2f}")

    # Step 2: Configure engine
    header("Step 2: Configure Evolution Engine")
    llm = AnthropicClient(api_key=api_key, default_model=model)

    config = EngineConfig(
        evolution=EvolutionConfig(
            symbol="BTCUSDT",
            timeframe="1h",
            generations=rounds,
            population_size=population,
            is_oos_ratio=0.7,
            temperature=0.7,
            model=model,
        ),
        selection=SelectionConfig(
            top_n=10,
            # Relaxed thresholds for small mock data
            min_is_trade_count=1,
            min_is_sharpe=-999,
            min_oos_trade_count=1,
            min_oos_sharpe=-999,
            min_oos_profit_factor=0,
            min_oos_win_rate=0,
            max_oos_drawdown_pct=100,
        ),
    )
    print(f"  IS/OOS split: {config.evolution.is_oos_ratio:.0%} / {1 - config.evolution.is_oos_ratio:.0%}")
    print(f"  Selection: relaxed (accepting all for pipeline test)")

    # Step 3: Run evolution
    header("Step 3: Running Evolution (LIVE LLM calls)")
    start_time = time.time()

    try:
        run = await llm_engine_evolve(llm, config, series)
    except LLMError as e:
        print(f"\n  LLM ERROR: {e}")
        print(f"  This might be a rate limit or API issue.")
        await llm.close()
        return {"error": str(e)}
    except Exception as e:
        print(f"\n  UNEXPECTED ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        await llm.close()
        return {"error": str(e)}

    elapsed = time.time() - start_time

    # Step 4: Results
    header("Results Summary")
    summary = run.summary
    print(f"\n  Run ID: {summary['run_id']}")
    print(f"  Generations: {summary['generations']}")
    print(f"  Total hypotheses: {summary['total_hypotheses']}")
    print(f"  Total backtests: {summary['total_backtests']}")
    print(f"  LLM tokens: {summary['total_llm_tokens']:,}")
    print(f"  Graduated: {summary['graduated']}")
    print(f"  Eliminated: {summary['eliminated']}")
    print(f"  Time: {elapsed:.1f}s")

    # Estimate cost (Haiku: $0.80/MTok input, $4/MTok output)
    # Rough: assume 60% input, 40% output tokens
    total_tokens = summary['total_llm_tokens']
    est_input = total_tokens * 0.6
    est_output = total_tokens * 0.4
    est_cost = (est_input * 0.80 + est_output * 4.0) / 1_000_000
    print(f"  Est. cost: ~${est_cost:.4f}")

    # Graduated strategies
    header("Graduated Strategies (Survivors)")
    if run.graduated:
        for i, h in enumerate(run.graduated, 1):
            print_hypothesis(h, i)
    else:
        print("\n  No strategies graduated.")
        print("  (This is expected with mock data + relaxed thresholds)")

    # All hypotheses sorted by OOS Sharpe
    header("All Hypotheses (by OOS Sharpe)")
    sorted_hyps = sorted(
        [h for h in run.hypotheses if h.fitness_oos],
        key=lambda h: h.fitness_oos.sharpe_ratio,
        reverse=True,
    )
    for i, h in enumerate(sorted_hyps[:10], 1):
        print_hypothesis(h, i)

    # Graveyard
    header("Strategy Graveyard")
    if run.graveyard:
        print(f"\n  {len(run.graveyard)} eliminated:")
        for h in run.graveyard[:10]:
            reason = h.elimination_reason or "ranked below top N"
            print(f"    [X] {h.pattern.name} (gen {h.generation}) -- {reason}")
    else:
        print("\n  (empty graveyard)")

    # Token breakdown per LLM call
    header("Done")
    print(f"\n  Pipeline completed in {elapsed:.1f}s")
    print(f"  Total tokens: {total_tokens:,}")
    print(f"  Model: {model}")
    print()

    await llm.close()
    return summary


async def llm_engine_evolve(llm, config, series):
    """Wrapper that adds extra logging around the engine."""
    engine = EvolutionEngine(llm, config)

    # Patch the generator to log raw LLM responses
    original_complete = llm.complete.__func__ if hasattr(llm.complete, '__func__') else None

    async def logged_complete(self, messages, **kwargs):
        logger.info(f"LLM call: model={kwargs.get('model', 'default')}, "
                    f"temp={kwargs.get('temperature', 0.7)}, "
                    f"max_tokens={kwargs.get('max_tokens', 4096)}")

        # Log prompt snippet
        if messages:
            prompt_preview = messages[-1].content[:200]
            logger.info(f"Prompt preview: {prompt_preview}...")

        response = await AnthropicClient.complete(self, messages, **kwargs)

        logger.info(f"Response: {response.input_tokens} in + {response.output_tokens} out tokens")

        # Log response snippet (first 300 chars)
        content_preview = response.content[:300]
        logger.info(f"Response preview: {content_preview}")

        # Check if it's valid JSON
        try:
            response.parse_json()
            logger.info("JSON parse: OK")
        except ValueError as e:
            logger.warning(f"JSON parse FAILED: {e}")
            logger.warning(f"Full response:\n{response.content}")

        return response

    # Monkey-patch for logging
    import types
    llm.complete = types.MethodType(logged_complete, llm)

    return await engine.evolve(series)


def main():
    parser = argparse.ArgumentParser(description="Evolution Engine LIVE test")
    parser.add_argument("--rounds", type=int, default=2, help="Number of evolution rounds")
    parser.add_argument("--pop", type=int, default=3, help="Population size per round")
    parser.add_argument("--model", type=str, default="claude-haiku-4-5-20251001",
                        help="Anthropic model ID")
    parser.add_argument("--bars", type=int, default=500, help="Number of mock OHLCV bars")
    args = parser.parse_args()

    summary = asyncio.run(run_live_test(
        rounds=args.rounds,
        population=args.pop,
        model=args.model,
        bars=args.bars,
    ))

    if "error" in summary:
        sys.exit(1)


if __name__ == "__main__":
    main()

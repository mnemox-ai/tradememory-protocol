#!/usr/bin/env python3
"""Evolution Engine with REAL Binance data + Real Anthropic API.

Fetches BTCUSDT 1H from Binance (last 3 months), runs evolution with Haiku.

Usage:
    python scripts/research/evolution_binance_test.py
    python scripts/research/evolution_binance_test.py --rounds 3 --pop 5 --months 3
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            k, v = key.strip(), value.strip()
            if v:
                os.environ[k] = v

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import Timeframe
from tradememory.evolution.engine import EngineConfig, EvolutionEngine
from tradememory.evolution.llm import AnthropicClient, LLMError
from tradememory.evolution.models import (
    EvolutionConfig,
    Hypothesis,
    HypothesisStatus,
)
from tradememory.evolution.selector import SelectionConfig

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("evolution_binance")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)

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


async def main(
    rounds: int = 2,
    population: int = 5,
    model: str = "claude-haiku-4-5-20251001",
    months: int = 3,
) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found in environment or .env")
        sys.exit(1)

    header(f"Evolution Engine — Binance BTCUSDT Real Data + {model}")
    print(f"\n  Model: {model}")
    print(f"  Rounds: {rounds}")
    print(f"  Population: {population}/round")
    print(f"  Data: BTCUSDT 1H, last {months} months from Binance")

    # Step 1: Fetch real data from Binance
    header("Step 1: Fetch BTCUSDT 1H from Binance")
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=months * 30)

    binance = BinanceDataSource()
    try:
        series = await binance.fetch_ohlcv(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            start=start_dt,
            end=end_dt,
        )
    except Exception as e:
        print(f"  ERROR fetching from Binance: {e}")
        await binance.close()
        return {"error": str(e)}

    await binance.close()

    closes = [b.close for b in series.bars]
    print(f"  Symbol: {series.symbol}")
    print(f"  Period: {series.start} -> {series.end}")
    print(f"  Bars: {series.count}")
    print(f"  Price: ${min(closes):,.2f} - ${max(closes):,.2f}")
    print(f"  Source: Binance public API (real data)")

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
            min_is_trade_count=3,
            min_is_sharpe=-5.0,
            min_oos_trade_count=2,
            min_oos_sharpe=-5.0,
            min_oos_profit_factor=0.0,
            min_oos_win_rate=0.0,
            max_oos_drawdown_pct=80.0,
        ),
    )

    is_bars = int(series.count * 0.7)
    oos_bars = series.count - is_bars
    print(f"  IS/OOS split: 70/30 = {is_bars} IS / {oos_bars} OOS bars")
    print(f"  Selection: moderate thresholds (min 3 IS trades, 2 OOS trades)")

    # Step 3: Run evolution
    header("Step 3: Running Evolution (LIVE LLM + Real Data)")
    start_time = time.time()

    try:
        engine = EvolutionEngine(llm, config)
        run = await engine.evolve(series)
    except LLMError as e:
        print(f"\n  LLM ERROR: {e}")
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

    total_tokens = summary['total_llm_tokens']
    est_input = total_tokens * 0.6
    est_output = total_tokens * 0.4
    est_cost = (est_input * 0.80 + est_output * 4.0) / 1_000_000
    print(f"  Est. cost: ~${est_cost:.4f}")

    # Graduated
    header("Graduated Strategies (Survivors)")
    if run.graduated:
        for i, h in enumerate(run.graduated, 1):
            print_hypothesis(h, i)
    else:
        print("\n  No strategies graduated.")

    # All by OOS Sharpe
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

    header("Done")
    print(f"\n  Pipeline completed in {elapsed:.1f}s")
    print(f"  Total tokens: {total_tokens:,}")
    print(f"  Data: {series.count} REAL Binance bars ({months} months)")
    print(f"  Model: {model}")
    print()

    await llm.close()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evolution with Binance real data")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--pop", type=int, default=5)
    parser.add_argument("--model", type=str, default="claude-haiku-4-5-20251001")
    parser.add_argument("--months", type=int, default=3)
    args = parser.parse_args()

    summary = asyncio.run(main(
        rounds=args.rounds,
        population=args.pop,
        model=args.model,
        months=args.months,
    ))

    if isinstance(summary, dict) and "error" in summary:
        sys.exit(1)

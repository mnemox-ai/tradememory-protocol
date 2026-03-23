#!/usr/bin/env python3
"""Phase 15 Exp 4b Step 0: Manual Single LLM Evolution Transition.

Runs EvolutionEngine.evolve() on 1st IS window (BTCUSDT 2020-01 to 2020-04).
Observes:
1. LLM hypothesis structure (conditions, features used)
2. Actual M (total_backtests, len(hypotheses))
3. API cost (total_llm_tokens)
4. raw Sharpe magnitude

Gate: If ALL hypotheses only use hour_utc + trend_12h_pct → STOP (no structural novelty).

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    set ANTHROPIC_API_KEY=sk-ant-...
    python scripts/research/run_llm_step0.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import Timeframe
from tradememory.evolution.engine import EngineConfig, EvolutionEngine
from tradememory.evolution.llm import AnthropicClient
from tradememory.evolution.models import EvolutionConfig


GRID_ONLY_FIELDS = {"hour_utc", "trend_12h_pct"}


def analyze_hypothesis(h, idx):
    """Analyze a single hypothesis for structural novelty."""
    fields_used = set()
    ops_used = set()
    for cond in h.pattern.entry_condition.conditions:
        fields_used.add(cond.field)
        ops_used.add(cond.op.value)

    # Check validity conditions for extra features
    vc = h.pattern.validity_conditions
    validity_fields = []
    if vc.regime:
        validity_fields.append(f"regime={vc.regime}")
    if vc.volatility_regime:
        validity_fields.append(f"volatility_regime={vc.volatility_regime}")
    if vc.session:
        validity_fields.append(f"session={vc.session}")
    if vc.min_atr_d1 is not None or vc.max_atr_d1 is not None:
        validity_fields.append(f"atr_d1=[{vc.min_atr_d1}, {vc.max_atr_d1}]")

    novel_fields = fields_used - GRID_ONLY_FIELDS
    is_novel = len(novel_fields) > 0 or len(validity_fields) > 0

    is_sharpe = h.fitness_is.sharpe_ratio if h.fitness_is else None
    oos_sharpe = h.fitness_oos.sharpe_ratio if h.fitness_oos else None
    is_trades = h.fitness_is.trade_count if h.fitness_is else 0

    print(f"\n  [{idx+1}] {h.pattern.name}")
    print(f"      Direction: {h.pattern.entry_condition.direction}")
    print(f"      Conditions ({len(h.pattern.entry_condition.conditions)}):")
    for c in h.pattern.entry_condition.conditions:
        print(f"        - {c.field} {c.op.value} {c.value}")
    print(f"      Exit: SL={h.pattern.exit_condition.stop_loss_atr}xATR, "
          f"TP={h.pattern.exit_condition.take_profit_atr}xATR, "
          f"hold<={h.pattern.exit_condition.max_holding_bars}")
    if validity_fields:
        print(f"      Validity: {', '.join(validity_fields)}")
    print(f"      Fields: {sorted(fields_used)} | Ops: {sorted(ops_used)}")
    print(f"      IS Sharpe: {is_sharpe:.4f} | IS trades: {is_trades}" if is_sharpe is not None else "      IS: N/A")
    print(f"      OOS Sharpe: {oos_sharpe:.4f}" if oos_sharpe is not None else "      OOS: N/A")
    print(f"      Status: {h.status.value} | Gen: {h.generation}")
    print(f"      NOVEL: {'YES' if is_novel else 'NO'} (novel fields: {sorted(novel_fields) if novel_fields else 'none'})")

    return {
        "name": h.pattern.name,
        "direction": h.pattern.entry_condition.direction,
        "conditions": [
            {"field": c.field, "op": c.op.value, "value": c.value}
            for c in h.pattern.entry_condition.conditions
        ],
        "exit": {
            "sl_atr": h.pattern.exit_condition.stop_loss_atr,
            "tp_atr": h.pattern.exit_condition.take_profit_atr,
            "max_holding_bars": h.pattern.exit_condition.max_holding_bars,
        },
        "validity": {k: v for k, v in h.pattern.validity_conditions.model_dump().items() if v is not None},
        "fields_used": sorted(fields_used),
        "ops_used": sorted(ops_used),
        "is_novel": is_novel,
        "novel_fields": sorted(novel_fields),
        "is_sharpe": is_sharpe,
        "oos_sharpe": oos_sharpe,
        "is_trades": is_trades,
        "status": h.status.value,
        "generation": h.generation,
    }


async def main():
    print("=" * 70)
    print("Phase 15 Exp 4b Step 0: LLM Evolution Single Transition")
    print("=" * 70)

    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    # --- Fetch data ---
    is_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    is_end = datetime(2020, 4, 1, tzinfo=timezone.utc)

    print(f"\n[1/3] Fetching BTCUSDT 1H data ({is_start.date()} to {is_end.date()})...")
    binance = BinanceDataSource()
    try:
        series = await binance.fetch_ohlcv(
            symbol="BTCUSDT",
            timeframe=Timeframe.H1,
            start=is_start,
            end=is_end,
        )
    finally:
        await binance.close()

    print(f"  Bars: {series.count}")
    print(f"  Period: {series.start} -> {series.end}")

    # --- Run Evolution ---
    print("\n[2/3] Running EvolutionEngine (3 generations, pop=10)...")
    llm = AnthropicClient(api_key=api_key)
    config = EngineConfig(
        evolution=EvolutionConfig(
            symbol="BTCUSDT",
            timeframe="1h",
            generations=3,
            population_size=10,
        )
    )
    engine = EvolutionEngine(llm, config)

    t0 = time.time()
    run = await engine.evolve(series)
    elapsed = time.time() - t0
    await llm.close()

    # --- Analyze Results ---
    print(f"\n[3/3] Results (took {elapsed:.1f}s)")
    print(f"  Run ID: {run.run_id}")
    print(f"  Total hypotheses: {len(run.hypotheses)}")
    print(f"  Graduated: {len(run.graduated)}")
    print(f"  Eliminated: {len(run.graveyard)}")
    print(f"  Total backtests: {run.total_backtests}")
    print(f"  Total LLM tokens: {run.total_llm_tokens}")
    print(f"  M (IS hypotheses tested) = {len(run.hypotheses)}")

    # Estimate cost (Sonnet 4 pricing)
    input_cost = run.total_llm_tokens * 0.6 * 3 / 1_000_000  # rough: 60% input tokens
    output_cost = run.total_llm_tokens * 0.4 * 15 / 1_000_000  # rough: 40% output tokens
    est_cost = input_cost + output_cost
    print(f"  Estimated cost this run: ${est_cost:.4f}")
    print(f"  Estimated cost 23 periods: ${est_cost * 23:.4f}")

    # Analyze each hypothesis
    print("\n" + "=" * 70)
    print("HYPOTHESIS ANALYSIS")
    print("=" * 70)

    all_analyses = []
    novel_count = 0
    all_fields = set()

    for i, h in enumerate(run.hypotheses):
        analysis = analyze_hypothesis(h, i)
        all_analyses.append(analysis)
        if analysis["is_novel"]:
            novel_count += 1
        all_fields.update(analysis["fields_used"])

    # Summary
    print("\n" + "=" * 70)
    print("STRUCTURAL NOVELTY SUMMARY")
    print("=" * 70)
    print(f"  Total hypotheses: {len(run.hypotheses)}")
    print(f"  Novel (uses fields beyond hour+trend): {novel_count}/{len(run.hypotheses)}")
    print(f"  All fields used across hypotheses: {sorted(all_fields)}")
    print(f"  Grid-only fields: {sorted(GRID_ONLY_FIELDS)}")
    print(f"  Novel fields: {sorted(all_fields - GRID_ONLY_FIELDS)}")

    # Gate decision
    if novel_count == 0:
        print("\n  ** GATE: FAIL — No structural novelty. All hypotheses use only hour+trend.")
        print("  ** STOP: Layer 2 experiment not worth running.")
        gate_result = "FAIL"
    else:
        print(f"\n  ** GATE: PASS — {novel_count}/{len(run.hypotheses)} hypotheses have structural novelty.")
        print("  ** PROCEED to Exp 4b LLM WFO pilot.")
        gate_result = "PASS"

    # Graduated hypotheses detail
    if run.graduated:
        print("\n" + "-" * 40)
        print("GRADUATED STRATEGIES (survived IS+OOS)")
        for i, g in enumerate(run.graduated):
            print(f"\n  Graduated #{i+1}: {g.pattern.name}")
            print(f"    IS Sharpe: {g.fitness_is.sharpe_ratio:.4f}" if g.fitness_is else "    IS: N/A")
            print(f"    OOS Sharpe: {g.fitness_oos.sharpe_ratio:.4f}" if g.fitness_oos else "    OOS: N/A")

    # Save results
    output = {
        "step": "Step 0 — Manual Single Transition",
        "date": datetime.now(timezone.utc).isoformat(),
        "data_period": f"{is_start.date()} to {is_end.date()}",
        "bars": series.count,
        "config": {
            "generations": 3,
            "population_size": 10,
            "model": config.evolution.model or "claude-sonnet-4-20250514",
        },
        "results": {
            "total_hypotheses": len(run.hypotheses),
            "graduated": len(run.graduated),
            "eliminated": len(run.graveyard),
            "total_backtests": run.total_backtests,
            "total_llm_tokens": run.total_llm_tokens,
            "M_is_hypotheses": len(run.hypotheses),
            "elapsed_seconds": round(elapsed, 1),
            "estimated_cost_usd": round(est_cost, 4),
            "estimated_cost_23_periods_usd": round(est_cost * 23, 4),
        },
        "novelty": {
            "gate_result": gate_result,
            "novel_count": novel_count,
            "total_count": len(run.hypotheses),
            "all_fields_used": sorted(all_fields),
            "novel_fields": sorted(all_fields - GRID_ONLY_FIELDS),
        },
        "hypotheses": all_analyses,
    }

    output_path = Path(__file__).parent.parent.parent / "validation" / "llm_step0_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\n  Results saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())

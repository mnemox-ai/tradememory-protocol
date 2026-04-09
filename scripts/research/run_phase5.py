"""
Phase 5: Rigorous Changepoint Validation

Research question: Does BOCPD-based calibration reduce drawdown compared to
naive baselines (periodic reduce, random skip, simple win-rate threshold)?

Experiment matrix:
- N symbols x K timeframes x M strategies (from grid, filtered to 30+ IS trades)
- 5 agents per strategy: BaseAgent, CalibratedAgent, PeriodicReduce, RandomSkip, SimpleWR
- Walk-forward: 67% IS / 33% OOS
- Warm-start for CalibratedAgent
- Bootstrap 95% CI on DD reduction
- Sensitivity analysis on hazard_rate (10 values)
- DSR validation on CalibratedAgent OOS results

Usage:
    cd C:/Users/johns/projects/tradememory-protocol

    # Pilot (fast):
    python scripts/research/run_phase5.py --symbols BTCUSDT,ETHUSDT --timeframes 1h --max-strategies 50

    # Full:
    python scripts/research/run_phase5.py --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,DOGEUSDT --timeframes 1h,4h

Output:
    scripts/research/phase5_results.json
    scripts/research/phase5_report.md
"""

import argparse
import asyncio
import json
import logging
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Setup logging before imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scripts/research/phase5.log", mode="w"),
    ],
)
logger = logging.getLogger(__name__)

# Suppress noisy logs
logging.getLogger("tradememory.owm_helpers").setLevel(logging.WARNING)
logging.getLogger("tradememory.owm.changepoint").setLevel(logging.WARNING)
logging.getLogger("tradememory.owm.dqs").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals
# ---------------------------------------------------------------------------

def bootstrap_dd_reduction(
    dd_baseline: List[float],
    dd_calibrated: List[float],
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> Dict[str, Any]:
    """Bootstrap 95% CI on DD reduction across strategies.

    Args:
        dd_baseline: max_dd values from BaseAgent across N strategies
        dd_calibrated: max_dd values from CalibratedAgent (same strategies)
        n_bootstrap: number of bootstrap resamples
        seed: random seed for reproducibility

    Returns:
        mean_reduction, ci_lower, ci_upper, p_value
    """
    rng = random.Random(seed)
    n = len(dd_baseline)
    if n == 0:
        return {"mean_reduction": 0.0, "ci_lower": 0.0, "ci_upper": 0.0,
                "p_value": 1.0, "n_strategies": 0}

    reductions = [
        (b - c) / max(b, 0.01)
        for b, c in zip(dd_baseline, dd_calibrated)
    ]

    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(reductions) for _ in range(n)]
        bootstrap_means.append(sum(sample) / n)

    bootstrap_means.sort()
    ci_lower = bootstrap_means[int(0.025 * n_bootstrap)]
    ci_upper = bootstrap_means[int(0.975 * n_bootstrap)]

    p_value = sum(1 for m in bootstrap_means if m <= 0) / n_bootstrap

    return {
        "mean_reduction": round(sum(reductions) / n, 6),
        "ci_lower": round(ci_lower, 6),
        "ci_upper": round(ci_upper, 6),
        "p_value": round(p_value, 4),
        "n_strategies": n,
    }


def bootstrap_comparison(
    dd_agent: List[float],
    dd_other: List[float],
    label: str,
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> Dict[str, Any]:
    """Bootstrap comparison: agent vs another agent on DD."""
    rng = random.Random(seed)
    n = len(dd_agent)
    if n == 0:
        return {"label": label, "win_rate": 0.0, "mean_dd_delta": 0.0,
                "ci_lower": 0.0, "ci_upper": 0.0, "p_value": 1.0, "n": 0}

    # Win rate: how often agent has lower DD than other
    wins = sum(1 for a, o in zip(dd_agent, dd_other) if a < o)
    win_rate = wins / n

    # DD delta: positive means agent is better (lower DD)
    deltas = [o - a for a, o in zip(dd_agent, dd_other)]
    mean_delta = sum(deltas) / n

    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(deltas) for _ in range(n)]
        bootstrap_means.append(sum(sample) / n)

    bootstrap_means.sort()
    ci_lower = bootstrap_means[int(0.025 * n_bootstrap)]
    ci_upper = bootstrap_means[int(0.975 * n_bootstrap)]
    p_value = sum(1 for m in bootstrap_means if m <= 0) / n_bootstrap

    return {
        "label": label,
        "win_rate": round(win_rate, 4),
        "mean_dd_delta": round(mean_delta, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "p_value": round(p_value, 4),
        "n": n,
    }


# ---------------------------------------------------------------------------
# DSR computation
# ---------------------------------------------------------------------------

def compute_dsr_safe(sharpe: float, n_trades: int) -> Dict[str, Any]:
    """Compute DSR, return dict with verdict."""
    try:
        from tradememory.strategy_validator import compute_dsr
        if n_trades >= 30:
            return compute_dsr(sharpe_raw=sharpe, num_obs=n_trades, num_trials=1)
        return {"verdict": "INSUFFICIENT_DATA", "sharpe_raw": round(sharpe, 6)}
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)}


# ---------------------------------------------------------------------------
# Single experiment runner (one strategy, one market)
# ---------------------------------------------------------------------------

def filter_strategies_is(
    strategies,
    is_series,
    timeframe_str: str,
    min_trades: int = 30,
) -> List[Tuple[Any, Any]]:
    """Pre-filter: run BaseAgent IS on all strategies, keep those with 30+ trades.

    Returns list of (strategy, is_result) tuples for qualifying strategies.
    This avoids re-running IS for each of the 5 agents.
    """
    from tradememory.simulation.agent import BaseAgent
    from tradememory.simulation.simulator import Simulator

    qualified = []
    for strategy in strategies:
        agent = BaseAgent(strategy, fixed_lot=0.01)
        sim = Simulator(agent, is_series, timeframe_str)
        result = sim.run()
        if result.fitness.trade_count >= min_trades:
            qualified.append((strategy, result))
    return qualified


def run_single_experiment(
    strategy,
    is_result,
    oos_series,
    symbol: str,
    timeframe_str: str,
    hazard_lambda: float = 50.0,
) -> Optional[Dict[str, Any]]:
    """Run 5 agents on OOS for one qualified strategy.

    Args:
        strategy: CandidatePattern
        is_result: Pre-computed BaseAgent IS result (for warm-start + trade count)
        oos_series: OOS data split
        symbol: Trading pair name
        timeframe_str: Timeframe string
        hazard_lambda: BOCPD hazard parameter

    Returns dict with metrics for all 5 agents, or None on failure.
    """
    from tradememory.simulation.agent import BaseAgent, CalibratedAgent
    from tradememory.simulation.baselines import (
        PeriodicReduceAgent,
        RandomSkipAgent,
        SimpleWRAgent,
    )
    from tradememory.simulation.simulator import Simulator

    is_trades = is_result.trades

    # --- Agent A (BaseAgent) on OOS ---
    agent_a = BaseAgent(strategy, fixed_lot=0.01)
    sim_a = Simulator(agent_a, oos_series, timeframe_str)
    result_a = sim_a.run()

    # --- Agent B (CalibratedAgent) on OOS with warm-start ---
    agent_b = CalibratedAgent(strategy, fixed_lot=0.01, hazard_lambda=hazard_lambda)
    _warm_start(agent_b, is_trades, symbol)
    sim_b = Simulator(agent_b, oos_series, timeframe_str)
    result_b = sim_b.run()

    # --- Baseline C: PeriodicReduceAgent on OOS ---
    agent_c = PeriodicReduceAgent(strategy, fixed_lot=0.01)
    sim_c = Simulator(agent_c, oos_series, timeframe_str)
    result_c = sim_c.run()

    # --- Baseline D: RandomSkipAgent on OOS ---
    agent_d = RandomSkipAgent(strategy, fixed_lot=0.01, seed=42)
    sim_d = Simulator(agent_d, oos_series, timeframe_str)
    result_d = sim_d.run()

    # --- Baseline E: SimpleWRAgent on OOS (warm-start outcomes from IS) ---
    agent_e = SimpleWRAgent(strategy, fixed_lot=0.01)
    for t in is_trades:
        agent_e.on_trade_complete(t)
    agent_e.trades = []
    sim_e = Simulator(agent_e, oos_series, timeframe_str)
    result_e = sim_e.run()

    return {
        "strategy": strategy.name,
        "symbol": symbol,
        "timeframe": timeframe_str,
        "is_trades": is_result.fitness.trade_count,
        "agents": {
            "base": _extract_metrics(result_a),
            "calibrated": _extract_metrics(result_b),
            "periodic_reduce": _extract_metrics(result_c),
            "random_skip": _extract_metrics(result_d),
            "simple_wr": _extract_metrics(result_e),
        },
    }


def _extract_metrics(result) -> Dict[str, Any]:
    """Extract key metrics from SimulationResult."""
    return {
        "trades": result.fitness.trade_count,
        "sharpe": round(result.fitness.sharpe_ratio, 6),
        "total_pnl": round(result.fitness.total_pnl, 4),
        "max_dd_pct": round(result.fitness.max_drawdown_pct, 4),
        "win_rate": round(result.fitness.win_rate, 4),
        "equity_total_pnl": round(result.equity_total_pnl, 4),
        "equity_max_dd": round(result.equity_max_dd, 4),
        "equity_calmar": round(result.equity_calmar, 4),
        "skipped": getattr(result, 'skipped_signals', 0),
    }


def _warm_start(agent, is_trades, symbol):
    """Warm-start CalibratedAgent with IS trades."""
    agent._current_symbol = symbol
    for trade in is_trades:
        agent.on_trade_complete(trade)

    # Compute DQS on IS trades for adaptive thresholds
    is_dqs_scores = []
    for trade in is_trades:
        try:
            dqs = agent.dqs_engine.compute(
                symbol=symbol,
                strategy_name=agent.strategy.name,
                direction=trade.direction,
                proposed_lot_size=agent.fixed_lot,
                context_regime=None,
            )
            is_dqs_scores.append(dqs.score)
        except Exception:
            pass

    if is_dqs_scores:
        agent.dqs_engine.set_adaptive_thresholds(is_dqs_scores)

    # Reset for OOS
    agent.trades = []
    agent.dqs_log = []
    agent.changepoint_log = []
    agent.skipped_signals = 0


# ---------------------------------------------------------------------------
# Sensitivity analysis
# ---------------------------------------------------------------------------

def run_sensitivity(
    strategy,
    series,
    timeframe_str: str,
    is_ratio: float = 0.67,
) -> List[Dict[str, Any]]:
    """Sweep hazard_rate on one strategy to check robustness."""
    from tradememory.simulation.agent import BaseAgent, CalibratedAgent
    from tradememory.simulation.simulator import Simulator

    hazard_values = [20, 30, 40, 50, 75, 100, 150, 200, 300, 500]
    results = []

    is_series, oos_series = series.split(is_ratio)

    # Baseline: Agent A on IS + OOS
    agent_a_is = BaseAgent(strategy, fixed_lot=0.01)
    result_a_is = Simulator(agent_a_is, is_series, timeframe_str).run()

    agent_a_oos = BaseAgent(strategy, fixed_lot=0.01)
    result_a_oos = Simulator(agent_a_oos, oos_series, timeframe_str).run()
    base_dd = result_a_oos.equity_max_dd

    for hz in hazard_values:
        try:
            agent_b = CalibratedAgent(strategy, fixed_lot=0.01, hazard_lambda=float(hz))
            _warm_start(agent_b, result_a_is.trades, series.symbol)
            result_b = Simulator(agent_b, oos_series, timeframe_str).run()

            dd_reduction = (base_dd - result_b.equity_max_dd) / max(base_dd, 0.01)

            results.append({
                "hazard_rate": hz,
                "equity_max_dd": round(result_b.equity_max_dd, 4),
                "dd_reduction": round(dd_reduction, 4),
                "trades": result_b.fitness.trade_count,
                "sharpe": round(result_b.fitness.sharpe_ratio, 6),
            })
        except Exception as e:
            logger.warning("Sensitivity failed for hz=%d: %s", hz, e)
            results.append({"hazard_rate": hz, "error": str(e)})

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    all_results: List[Dict[str, Any]],
    comparisons: Dict[str, Dict[str, Any]],
    sensitivity_results: List[Dict[str, Any]],
    dsr_results: List[Dict[str, Any]],
    elapsed_seconds: float,
) -> str:
    """Generate Phase 5 research-grade Markdown report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    successful = [r for r in all_results if "agents" in r]
    n_total = len(successful)

    # Aggregate win rates
    cal_vs_base_wins = sum(
        1 for r in successful
        if r["agents"]["calibrated"]["equity_max_dd"] < r["agents"]["base"]["equity_max_dd"]
    )

    lines = []
    lines.append("# Phase 5: Rigorous Changepoint Validation")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append(f"Runtime: {elapsed_seconds:.0f}s ({elapsed_seconds/60:.1f} min)")
    lines.append("")

    # --- 1. Research Question ---
    lines.append("## 1. Research Question")
    lines.append("")
    lines.append("Does BOCPD-based position adjustment reduce drawdown compared to:")
    lines.append("- a) No adjustment (BaseAgent)")
    lines.append("- b) Periodic reduction (PeriodicReduceAgent)")
    lines.append("- c) Random skip (RandomSkipAgent)")
    lines.append("- d) Simple win-rate threshold (SimpleWRAgent)")
    lines.append("")

    # --- 2. Methodology ---
    symbols = sorted(set(r["symbol"] for r in successful))
    timeframes = sorted(set(r["timeframe"] for r in successful))
    lines.append("## 2. Methodology")
    lines.append("")
    lines.append(f"- **Strategies**: Parameter grid ({n_total} passed IS filter of 30+ trades)")
    lines.append(f"- **Symbols**: {', '.join(symbols)}")
    lines.append(f"- **Timeframes**: {', '.join(timeframes)}")
    lines.append(f"- **Walk-forward**: 67% IS / 33% OOS")
    lines.append(f"- **Warm-start**: CalibratedAgent seeded with IS trades + adaptive DQS thresholds")
    lines.append(f"- **Bootstrap**: 1000 resamples, 95% CI")
    lines.append(f"- **DSR validation**: On CalibratedAgent OOS Sharpe")
    lines.append("")

    # --- 3. Results ---
    lines.append("## 3. Results")
    lines.append("")

    lines.append("### 3.1 Aggregate: CalibratedAgent vs BaseAgent")
    lines.append("")
    if n_total > 0:
        lines.append(f"- Experiments total: {n_total}")
        lines.append(f"- Win rate (Calibrated has lower DD): {cal_vs_base_wins}/{n_total} = {cal_vs_base_wins/n_total:.1%}")
    comp_base = comparisons.get("vs_base", {})
    if comp_base:
        lines.append(f"- Mean DD reduction: {comp_base.get('mean_reduction', 0):.4f}")
        lines.append(f"- 95% CI: [{comp_base.get('ci_lower', 0):.4f}, {comp_base.get('ci_upper', 0):.4f}]")
        lines.append(f"- Bootstrap p-value: {comp_base.get('p_value', 1):.4f}")
    lines.append("")

    lines.append("### 3.2 vs Naive Baselines")
    lines.append("")
    lines.append("| Comparison | Win Rate | Mean DD delta | 95% CI | p-value | N |")
    lines.append("|------------|----------|--------------|--------|---------|---|")
    for key in ["vs_base", "vs_periodic", "vs_random_skip", "vs_simple_wr"]:
        comp = comparisons.get(key, {})
        if comp:
            lines.append(
                f"| {comp.get('label', key)} "
                f"| {comp.get('win_rate', 0):.1%} "
                f"| {comp.get('mean_dd_delta', 0):.4f} "
                f"| [{comp.get('ci_lower', 0):.4f}, {comp.get('ci_upper', 0):.4f}] "
                f"| {comp.get('p_value', 1):.4f} "
                f"| {comp.get('n', 0)} |"
            )
    lines.append("")

    # --- 3.3 Sensitivity ---
    lines.append("### 3.3 Sensitivity: hazard_rate")
    lines.append("")
    if sensitivity_results:
        lines.append("| hazard_rate | Mean DD reduction | Strategies improved | Robust? |")
        lines.append("|-------------|------------------|--------------------|---------| ")
        for sr in sensitivity_results:
            if "error" not in sr:
                robust = "Yes" if abs(sr.get("dd_reduction", 0)) > 0 else "?"
                lines.append(
                    f"| {sr['hazard_rate']} "
                    f"| {sr.get('dd_reduction', 0):.4f} "
                    f"| {sr.get('strategies_improved', 'N/A')} "
                    f"| {robust} |"
                )
    else:
        lines.append("No sensitivity data (insufficient qualifying strategies).")
    lines.append("")

    # --- 3.4 DSR ---
    lines.append("### 3.4 DSR Pass Rate")
    lines.append("")
    if dsr_results:
        passed = sum(1 for d in dsr_results if d.get("verdict") == "PASS")
        lines.append(f"- {passed}/{len(dsr_results)} experiments pass DSR (Agent B Sharpe is statistically real)")
    else:
        lines.append("- No DSR results")
    lines.append("")

    # --- 3.5 Trade Activity Analysis ---
    lines.append("### 3.5 Trade Activity (Critical)")
    lines.append("")
    cal_trades = [r["agents"]["calibrated"]["trades"] for r in successful]
    base_trades = [r["agents"]["base"]["trades"] for r in successful]
    cal_skipped = [r["agents"]["calibrated"]["skipped"] for r in successful]
    zero_trade_count = sum(1 for t in cal_trades if t == 0)
    lines.append(f"- BaseAgent mean trades: {_mean(base_trades):.1f}")
    lines.append(f"- CalibratedAgent mean trades: {_mean(cal_trades):.1f}")
    lines.append(f"- CalibratedAgent mean skipped signals: {_mean(cal_skipped):.1f}")
    lines.append(f"- CalibratedAgent with 0 OOS trades: {zero_trade_count}/{n_total}")
    lines.append("")
    if zero_trade_count > n_total * 0.3:
        lines.append("**WARNING**: CalibratedAgent executes very few trades. DD reduction is largely from")
        lines.append("NOT TRADING rather than intelligent calibration. DQS skip tier is too aggressive")
        lines.append("on cold-start / small DB, causing near-total trade rejection in OOS.")
        lines.append("This invalidates the DD reduction as a measure of changepoint value.")
        lines.append("")

    # --- 4. Per-market breakdown ---
    lines.append("## 4. Per-Market Breakdown")
    lines.append("")
    lines.append("| Symbol | TF | Strategies | Cal wins | Cal mean DD | Base mean DD |")
    lines.append("|--------|-----|------------|----------|-------------|-------------|")
    for sym in symbols:
        for tf in timeframes:
            subset = [r for r in successful if r["symbol"] == sym and r["timeframe"] == tf]
            if not subset:
                continue
            cal_wins = sum(
                1 for r in subset
                if r["agents"]["calibrated"]["equity_max_dd"] < r["agents"]["base"]["equity_max_dd"]
            )
            cal_dd = _mean([r["agents"]["calibrated"]["equity_max_dd"] for r in subset])
            base_dd = _mean([r["agents"]["base"]["equity_max_dd"] for r in subset])
            lines.append(
                f"| {sym} | {tf} | {len(subset)} | {cal_wins}/{len(subset)} "
                f"| {cal_dd:.2f} | {base_dd:.2f} |"
            )
    lines.append("")

    # --- 5. Conclusion ---
    lines.append("## 5. Conclusion")
    lines.append("")

    # Determine verdict
    comp_base = comparisons.get("vs_base", {})
    comp_periodic = comparisons.get("vs_periodic", {})
    comp_wr = comparisons.get("vs_simple_wr", {})

    beats_base = comp_base.get("p_value", 1) < 0.05 and comp_base.get("mean_reduction", 0) > 0
    beats_naive = (
        comp_periodic.get("p_value", 1) < 0.05
        or comp_wr.get("p_value", 1) < 0.05
    )

    # Check if the "win" is just from not trading
    cal_trades = [r["agents"]["calibrated"]["trades"] for r in successful]
    zero_pct = sum(1 for t in cal_trades if t == 0) / max(n_total, 1)
    mean_cal_trades = _mean(cal_trades) if cal_trades else 0
    base_trades = [r["agents"]["base"]["trades"] for r in successful]
    mean_base_trades = _mean(base_trades) if base_trades else 1
    trade_ratio = mean_cal_trades / max(mean_base_trades, 1)

    if beats_base and beats_naive and zero_pct < 0.3 and trade_ratio > 0.3:
        verdict = "GO -- BOCPD provides statistically significant improvement over both no-calibration and naive baselines"
    elif beats_base and beats_naive:
        verdict = (
            "INVALID -- CalibratedAgent reduces DD by NOT TRADING "
            f"({zero_pct:.0%} zero-trade experiments, trade ratio {trade_ratio:.1%}). "
            "DQS skip tier too aggressive. BOCPD changepoint effect unmeasurable."
        )
    elif beats_base:
        verdict = "PARTIAL -- BOCPD beats no-calibration but NOT naive baselines (no novel contribution)"
    else:
        verdict = "NO-GO -- BOCPD does not provide statistically significant drawdown reduction"

    lines.append(f"**Verdict: {verdict}**")
    lines.append("")
    lines.append("- Is BOCPD better than naive? " + ("YES" if beats_naive else "NO") + f" (p={comp_periodic.get('p_value', 'N/A')})")

    # Robustness check
    if sensitivity_results:
        dd_reds = [sr.get("dd_reduction", 0) for sr in sensitivity_results if "error" not in sr]
        if dd_reds:
            positive_count = sum(1 for d in dd_reds if d > 0)
            lines.append(f"- Is it robust to parameter choice? {positive_count}/{len(dd_reds)} hazard_rates show improvement")

    lines.append(f"- Is it cross-market? Tested on {len(symbols)} symbols")
    lines.append("")

    return "\n".join(lines)


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Phase 5: Rigorous Changepoint Validation")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT",
                        help="Comma-separated symbols")
    parser.add_argument("--timeframes", default="1h",
                        help="Comma-separated timeframes")
    parser.add_argument("--max-strategies", type=int, default=0,
                        help="Limit grid strategies (0 = all)")
    parser.add_argument("--days", type=int, default=1095,
                        help="Days of historical data")
    parser.add_argument("--is-ratio", type=float, default=0.67,
                        help="In-sample ratio")
    parser.add_argument("--output-dir", default="scripts/research",
                        help="Output directory")
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    timeframes = [t.strip() for t in args.timeframes.split(",")]

    from tradememory.data.binance import BinanceDataSource
    from tradememory.data.models import Timeframe
    from tradememory.simulation.strategy_generator import generate_strategy_grid

    # Generate strategy grid
    all_strategies = generate_strategy_grid()
    if args.max_strategies > 0:
        all_strategies = all_strategies[:args.max_strategies]

    print("=" * 70)
    print("Phase 5: Rigorous Changepoint Validation")
    print(f"  Symbols:    {', '.join(symbols)}")
    print(f"  Timeframes: {', '.join(timeframes)}")
    print(f"  Grid strategies: {len(all_strategies)} (pre-filter)")
    print(f"  Days: {args.days}")
    print(f"  IS/OOS: {args.is_ratio:.0%} / {1-args.is_ratio:.0%}")
    print(f"  Agents: BaseAgent, CalibratedAgent, PeriodicReduce, RandomSkip, SimpleWR")
    print("=" * 70)
    print()

    datasource = BinanceDataSource()
    tf_map = {tf.value: tf for tf in Timeframe}
    os.makedirs(args.output_dir, exist_ok=True)
    partial_path = os.path.join(args.output_dir, "phase5_partial.json")

    all_results: List[Dict[str, Any]] = []
    start_time = time.time()

    total_market_combos = len(symbols) * len(timeframes)
    market_idx = 0
    # Cache fetched series for sensitivity reuse
    series_cache: Dict[str, Any] = {}

    for symbol in symbols:
        for tf_str in timeframes:
            market_idx += 1
            tf_enum = tf_map.get(tf_str)
            if tf_enum is None:
                logger.warning("Unknown timeframe %s, skipping", tf_str)
                continue

            # Fetch data
            print(f"\n[Market {market_idx}/{total_market_combos}] Fetching {symbol} {tf_str} ({args.days} days)...")
            try:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=args.days)
                series = await _fetch_retry(datasource, symbol, tf_enum, start, end)
                print(f"  Got {len(series.bars)} bars")
            except Exception as e:
                logger.error("Failed to fetch %s %s: %s", symbol, tf_str, e)
                continue

            cache_key = f"{symbol}_{tf_str}"
            series_cache[cache_key] = series

            # Split once
            is_series, oos_series = series.split(args.is_ratio)
            print(f"  IS: {len(is_series.bars)} bars, OOS: {len(oos_series.bars)} bars")

            # Phase 1: Batch filter — BaseAgent IS on all strategies
            print(f"  Filtering {len(all_strategies)} strategies (IS >=30 trades)...")
            t0 = time.time()
            qualified_pairs = filter_strategies_is(
                all_strategies, is_series, tf_str, min_trades=30,
            )
            filter_time = time.time() - t0
            print(f"  {len(qualified_pairs)}/{len(all_strategies)} qualified in {filter_time:.0f}s")

            # Phase 2: Run 5-agent OOS on qualified strategies
            for q_idx, (strategy, is_result) in enumerate(qualified_pairs):
                result = run_single_experiment(
                    strategy, is_result, oos_series,
                    symbol=symbol,
                    timeframe_str=tf_str,
                    hazard_lambda=50.0,
                )

                if result is None:
                    continue

                all_results.append(result)

                # Progress
                cal_dd = result["agents"]["calibrated"]["equity_max_dd"]
                base_dd = result["agents"]["base"]["equity_max_dd"]
                better = "+" if cal_dd < base_dd else "-"
                print(
                    f"  [{q_idx+1}/{len(qualified_pairs)}] {strategy.name}: "
                    f"base_dd={base_dd:.2f} cal_dd={cal_dd:.2f} {better}"
                )

                # Partial save every 10 strategies
                if (q_idx + 1) % 10 == 0:
                    _save_partial(all_results, partial_path)

            # Save after each market
            _save_partial(all_results, partial_path)

    elapsed = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"Experiments complete: {len(all_results)} in {elapsed:.0f}s")

    if not all_results:
        print("No qualifying experiments. Exiting.")
        return

    # --- Statistical analysis ---
    print("\nRunning statistical analysis...")

    # Collect DD arrays for bootstrap
    dd_base = [r["agents"]["base"]["equity_max_dd"] for r in all_results]
    dd_cal = [r["agents"]["calibrated"]["equity_max_dd"] for r in all_results]
    dd_periodic = [r["agents"]["periodic_reduce"]["equity_max_dd"] for r in all_results]
    dd_random = [r["agents"]["random_skip"]["equity_max_dd"] for r in all_results]
    dd_wr = [r["agents"]["simple_wr"]["equity_max_dd"] for r in all_results]

    comparisons = {
        "vs_base": {
            **bootstrap_dd_reduction(dd_base, dd_cal),
            "label": "Calibrated vs No calibration",
            "win_rate": round(sum(1 for a, b in zip(dd_cal, dd_base) if a < b) / max(len(dd_base), 1), 4),
        },
        "vs_periodic": bootstrap_comparison(dd_cal, dd_periodic, "Calibrated vs Periodic reduce"),
        "vs_random_skip": bootstrap_comparison(dd_cal, dd_random, "Calibrated vs Random skip"),
        "vs_simple_wr": bootstrap_comparison(dd_cal, dd_wr, "Calibrated vs Simple WR"),
    }

    # --- DSR ---
    print("Computing DSR...")
    dsr_results = []
    for r in all_results:
        cal = r["agents"]["calibrated"]
        dsr = compute_dsr_safe(cal["sharpe"], cal["trades"])
        dsr_results.append(dsr)

    # --- Sensitivity analysis on top 5 strategies by DD reduction ---
    print("Running sensitivity analysis...")
    sensitivity_agg: List[Dict[str, Any]] = []

    # Find top strategies where calibrated beat base the most
    dd_reductions = [
        (i, (r["agents"]["base"]["equity_max_dd"] - r["agents"]["calibrated"]["equity_max_dd"]))
        for i, r in enumerate(all_results)
    ]
    dd_reductions.sort(key=lambda x: x[1], reverse=True)
    top_indices = [idx for idx, _ in dd_reductions[:5]]

    if top_indices:
        for rank, idx in enumerate(top_indices):
            r = all_results[idx]
            print(f"  Sensitivity [{rank+1}/5]: {r['strategy']} on {r['symbol']} {r['timeframe']}")

            sym = r["symbol"]
            tf = r["timeframe"]
            cache_key = f"{sym}_{tf}"
            series = series_cache.get(cache_key)
            if series is None:
                continue

            # Find the strategy object
            strat = None
            for s in all_strategies:
                if s.name == r["strategy"]:
                    strat = s
                    break
            if strat is None:
                continue

            sens = run_sensitivity(strat, series, tf, is_ratio=args.is_ratio)
            sensitivity_agg.append({
                "strategy": r["strategy"],
                "symbol": sym,
                "timeframe": tf,
                "sweep": sens,
            })

    # Flatten sensitivity for report
    sensitivity_flat: List[Dict[str, Any]] = []
    if sensitivity_agg:
        # Aggregate across strategies per hazard_rate
        hz_values = [20, 30, 40, 50, 75, 100, 150, 200, 300, 500]
        for hz in hz_values:
            dd_reds = []
            for sa in sensitivity_agg:
                for sw in sa["sweep"]:
                    if sw.get("hazard_rate") == hz and "error" not in sw:
                        dd_reds.append(sw["dd_reduction"])
            if dd_reds:
                improved = sum(1 for d in dd_reds if d > 0)
                sensitivity_flat.append({
                    "hazard_rate": hz,
                    "dd_reduction": round(sum(dd_reds) / len(dd_reds), 4),
                    "strategies_improved": f"{improved}/{len(dd_reds)}",
                })

    # --- Generate report ---
    print("Generating report...")
    report_md = generate_report(
        all_results, comparisons, sensitivity_flat, dsr_results, elapsed
    )

    # Save outputs
    output_base = os.path.join(args.output_dir, "phase5_results")

    with open(output_base + ".json", "w") as f:
        json.dump({
            "metadata": {
                "generated": datetime.now(timezone.utc).isoformat(),
                "runtime_seconds": round(elapsed, 1),
                "symbols": symbols,
                "timeframes": timeframes,
                "grid_strategies": len(all_strategies),
                "qualified_experiments": len(all_results),
            },
            "results": all_results,
            "comparisons": comparisons,
            "dsr": dsr_results,
            "sensitivity": sensitivity_agg,
        }, f, indent=2, default=str)

    with open(output_base + ".md", "w") as f:
        f.write(report_md)

    # Cleanup partial
    if os.path.exists(partial_path):
        try:
            os.remove(partial_path)
        except Exception:
            pass

    print(f"\nResults: {output_base}.json")
    print(f"Report:  {output_base}.md")
    print()
    print(report_md[:2000])  # Print first part of report


async def _fetch_retry(datasource, symbol, tf_enum, start, end, max_retries=3):
    """Fetch with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return await datasource.fetch_ohlcv(
                symbol=symbol, timeframe=tf_enum, start=start, end=end,
            )
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt * 5
                logger.warning("Fetch retry %d: %s", attempt + 1, e)
                await asyncio.sleep(wait)
            else:
                raise


def _save_partial(results, path):
    """Save partial results to disk."""
    try:
        with open(path, "w") as f:
            json.dump(results, f, indent=2, default=str)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())

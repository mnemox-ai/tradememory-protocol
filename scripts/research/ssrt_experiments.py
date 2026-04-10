"""SSRT Phase 1 — Monte Carlo experiments comparing mSPRT vs baselines.

Run: python scripts/research/ssrt_experiments.py
Output: validation/ssrt/experiment_results.json + console summary table
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from tradememory.ssrt.core import MixtureSPRT
from tradememory.ssrt.regime import RegimeAwareNull
from tradememory.ssrt.simulator import DecaySimulator
from tradememory.ssrt.baselines import MaxDDBaseline, RollingSharpeBaseline, CUSUMBaseline
from tradememory.ssrt.models import TradeResult


@dataclass
class ExperimentResult:
    scenario: str
    method: str
    detected: bool
    detection_trade: int | None
    true_decay_trade: int | None
    detection_delay: int | None
    final_pnl: float
    pnl_saved: float


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS = {
    "no_decay": {
        "method": "no_decay",
        "n": 200,
        "params": {"mean": 0.5, "std": 1.5},
        "true_decay": None,
    },
    "sudden_death_50": {
        "method": "sudden_death",
        "n": 200,
        "params": {"decay_at": 50, "pre_mean": 0.5, "post_mean": -0.3, "std": 1.5},
        "true_decay": 50,
    },
    "sudden_death_100": {
        "method": "sudden_death",
        "n": 200,
        "params": {"decay_at": 100, "pre_mean": 0.5, "post_mean": -0.3, "std": 1.5},
        "true_decay": 100,
    },
    "linear_decay": {
        "method": "linear_decay",
        "n": 200,
        "params": {"decay_start": 50, "decay_end": 150, "pre_mean": 0.5, "post_mean": -0.3, "std": 1.5},
        "true_decay": 50,
    },
    "regime_specific": {
        "method": "regime_specific_decay",
        "n": 200,
        "params": {"decay_at": 50, "pre_mean": 0.5, "post_mean": -0.3, "safe_mean": 0.3, "std": 1.5},
        "true_decay": 50,
    },
}

N_SIMULATIONS = 500


def generate_trades(scenario: dict, seed: int) -> list[TradeResult]:
    """Generate trade sequence for a scenario."""
    method_name = scenario["method"]
    params = dict(scenario["params"])
    params["n_trades"] = scenario["n"]
    params["seed"] = seed
    return getattr(DecaySimulator, method_name)(**params)


def run_msprt(
    trades: list[TradeResult],
    use_regime: bool = False,
    null_mean: float = 0.0,
    sigma: float = 1.5,
    tau: float = 1.0,
) -> tuple[bool, int | None, float]:
    """Run mSPRT on trades. Returns (detected, detection_trade, final_pnl)."""
    msprt = MixtureSPRT(alpha=0.05, tau=tau, sigma=sigma, null_mean=null_mean, burn_in=20)
    regime_null = RegimeAwareNull(min_trades_per_regime=10) if use_regime else None

    cum_pnl = 0.0
    prev_regime = None

    for i, trade in enumerate(trades):
        cum_pnl += trade.pnl_r

        if regime_null is not None:
            regime_null.update(trade)
            rn_mean, rn_sigma = regime_null.get_null(trade.regime)
            # Reset mSPRT if regime changed
            if trade.regime != prev_regime and prev_regime is not None:
                msprt.reset(null_mean=rn_mean, sigma=rn_sigma)
            prev_regime = trade.regime

        verdict = msprt.update(trade.pnl_r)
        if verdict.decision == "RETIRE":
            return True, i + 1, cum_pnl

    return False, None, cum_pnl


def run_baseline(trades: list[TradeResult], baseline) -> tuple[bool, int | None, float]:
    """Run a baseline method. Returns (detected, detection_trade, final_pnl)."""
    baseline.reset()
    cum_pnl = 0.0
    for i, trade in enumerate(trades):
        cum_pnl += trade.pnl_r
        result = baseline.update(trade)
        if result == "RETIRE":
            return True, i + 1, cum_pnl
    return False, None, cum_pnl


def compute_full_pnl(trades: list[TradeResult]) -> float:
    """Cumulative P&L for full sequence."""
    return sum(t.pnl_r for t in trades)


def run_experiments() -> list[ExperimentResult]:
    """Run all Monte Carlo experiments."""
    results: list[ExperimentResult] = []
    total_cells = len(SCENARIOS) * 6  # 6 methods
    cell_count = 0

    for scenario_name, scenario_cfg in SCENARIOS.items():
        true_decay = scenario_cfg["true_decay"]

        # null_mean = pre_mean for calibrated mSPRT (strategy's expected baseline)
        pre_mean = scenario_cfg["params"].get("pre_mean", scenario_cfg["params"].get("mean", 0.5))
        std = scenario_cfg["params"].get("std", 1.5)

        methods = {
            "mSPRT":        lambda trades, pm=pre_mean, s=std: run_msprt(trades, use_regime=False, null_mean=pm, sigma=s),
            "mSPRT_regime": lambda trades, pm=pre_mean, s=std: run_msprt(trades, use_regime=True, null_mean=pm, sigma=s),
            "MaxDD_5R":     lambda trades: run_baseline(trades, MaxDDBaseline(threshold_r=5.0)),
            "MaxDD_8R":     lambda trades: run_baseline(trades, MaxDDBaseline(threshold_r=8.0)),
            "RollingSharpe": lambda trades: run_baseline(trades, RollingSharpeBaseline(window=30, consecutive=3)),
            "CUSUM":        lambda trades: run_baseline(trades, CUSUMBaseline(threshold=4.0, target_wr=0.5)),
        }

        for method_name, method_fn in methods.items():
            cell_count += 1
            t0 = time.time()

            for sim_idx in range(N_SIMULATIONS):
                trades = generate_trades(scenario_cfg, seed=sim_idx)
                full_pnl = compute_full_pnl(trades)

                detected, detection_trade, final_pnl = method_fn(trades)

                detection_delay = None
                if detected and true_decay is not None and detection_trade is not None:
                    detection_delay = detection_trade - true_decay

                pnl_saved = full_pnl - final_pnl if detected else 0.0

                results.append(ExperimentResult(
                    scenario=scenario_name,
                    method=method_name,
                    detected=detected,
                    detection_trade=detection_trade,
                    true_decay_trade=true_decay,
                    detection_delay=detection_delay,
                    final_pnl=round(final_pnl, 4),
                    pnl_saved=round(pnl_saved, 4),
                ))

            elapsed = time.time() - t0
            print(f"  [{cell_count}/{total_cells}] {scenario_name} x {method_name}: {elapsed:.1f}s")

    return results


def aggregate_results(results: list[ExperimentResult]) -> dict:
    """Compute per-scenario, per-method aggregate metrics."""
    from collections import defaultdict

    groups = defaultdict(list)
    for r in results:
        groups[(r.scenario, r.method)].append(r)

    aggregates = {}
    for (scenario, method), group in sorted(groups.items()):
        n = len(group)
        has_decay = group[0].true_decay_trade is not None

        detected_count = sum(1 for r in group if r.detected)

        if not has_decay:
            # Type I error (false retirement)
            type_i = detected_count / n
            type_ii = None
            delays = []
        else:
            type_i = None
            type_ii = 1.0 - detected_count / n  # miss rate
            delays = [r.detection_delay for r in group if r.detection_delay is not None]

        median_delay = float(np.median(delays)) if delays else None
        mean_pnl_saved = float(np.mean([r.pnl_saved for r in group]))

        aggregates[(scenario, method)] = {
            "type_i": type_i,
            "type_ii": type_ii,
            "median_delay": median_delay,
            "mean_pnl_saved": round(mean_pnl_saved, 2),
            "detection_rate": detected_count / n,
            "n_simulations": n,
        }

    return aggregates


def print_summary(aggregates: dict):
    """Print formatted summary table."""
    print("\n" + "=" * 100)
    print(f"{'Scenario':<20} | {'Method':<15} | {'Type I':>7} | {'Type II':>7} | {'Med Delay':>10} | {'Mean PnL Saved':>14} | {'Det Rate':>8}")
    print("-" * 100)

    prev_scenario = None
    for (scenario, method), agg in sorted(aggregates.items()):
        if scenario != prev_scenario and prev_scenario is not None:
            print("-" * 100)
        prev_scenario = scenario

        type_i_str = f"{agg['type_i']:.3f}" if agg['type_i'] is not None else "---"
        type_ii_str = f"{agg['type_ii']:.3f}" if agg['type_ii'] is not None else "---"
        delay_str = f"{agg['median_delay']:.0f}" if agg['median_delay'] is not None else "---"
        pnl_str = f"{agg['mean_pnl_saved']:+.2f}"
        det_str = f"{agg['detection_rate']:.3f}"

        print(f"{scenario:<20} | {method:<15} | {type_i_str:>7} | {type_ii_str:>7} | {delay_str:>10} | {pnl_str:>14} | {det_str:>8}")

    print("=" * 100)


def main():
    print(f"SSRT Phase 1 Experiments — {len(SCENARIOS)} scenarios x 6 methods x {N_SIMULATIONS} simulations")
    print(f"Total runs: {len(SCENARIOS) * 6 * N_SIMULATIONS}")
    print()

    t0 = time.time()
    results = run_experiments()
    total_time = time.time() - t0
    print(f"\nTotal time: {total_time:.1f}s")

    aggregates = aggregate_results(results)
    print_summary(aggregates)

    # Save results
    output_dir = Path(__file__).resolve().parents[2] / "validation" / "ssrt"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save raw results
    raw_path = output_dir / "experiment_results.json"
    with open(raw_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"\nRaw results saved to: {raw_path}")

    # Save aggregates
    agg_serializable = {f"{s}|{m}": v for (s, m), v in aggregates.items()}
    agg_path = output_dir / "experiment_aggregates.json"
    with open(agg_path, "w") as f:
        json.dump(agg_serializable, f, indent=2)
    print(f"Aggregates saved to: {agg_path}")


if __name__ == "__main__":
    main()

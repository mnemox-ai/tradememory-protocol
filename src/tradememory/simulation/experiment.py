"""A/B Experiment and Ablation study for TradeMemory calibration.

ABExperiment: Compare BaseAgent (A) vs CalibratedAgent (B) on the same data.
Ablation: Remove one calibration component at a time to measure individual impact.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tradememory.data.models import OHLCVSeries
from tradememory.evolution.models import CandidatePattern
from tradememory.simulation.agent import BaseAgent, CalibratedAgent, SimulatedTrade
from tradememory.simulation.simulator import SimulationResult, Simulator


@dataclass
class ComparisonReport:
    """A/B comparison between Agent A (baseline) and Agent B (calibrated)."""

    agent_a: SimulationResult
    agent_b: SimulationResult
    sharpe_improvement: float  # (B.sharpe - A.sharpe) / max(|A.sharpe|, 0.01)
    dd_reduction: float  # (A.max_dd - B.max_dd) / max(A.max_dd, 0.01)
    trades_skipped_by_b: int
    pnl_of_skipped_trades: float  # from A's perspective
    dqs_pnl_correlation: float  # Pearson r between DQS score and trade PnL
    statistical_significance: Dict[str, Any]  # paired t-test on trade PnLs


@dataclass
class AblationResult:
    """Result of removing one calibration component."""

    variant_name: str
    result: SimulationResult
    sharpe_delta: float  # vs full Agent B (negative = component was helpful)


class ABExperiment:
    """Run A/B comparison between BaseAgent and CalibratedAgent.

    Splits data into IS (training) / OOS (evaluation).
    Agent A runs on full data. Agent B learns on IS, evaluated on OOS.
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        series: OHLCVSeries,
        timeframe_str: str = "1h",
        is_ratio: float = 0.67,
    ):
        self.strategy = strategy
        self.series = series
        self.timeframe_str = timeframe_str
        self.is_ratio = is_ratio

    def run(self) -> ComparisonReport:
        """Run A/B experiment with IS/OOS split.

        1. Split data into IS (first is_ratio) and OOS (rest)
        2. Agent A: run on full OOS data (no learning)
        3. Agent B: learn on IS, then evaluate on OOS
        4. Compare OOS results
        """
        is_series, oos_series = self.series.split(self.is_ratio)

        # Agent A: baseline on OOS only
        agent_a = BaseAgent(self.strategy, fixed_lot=0.01)
        sim_a = Simulator(agent_a, oos_series, self.timeframe_str)
        result_a = sim_a.run()

        # Agent B: train on IS, evaluate on OOS
        agent_b = CalibratedAgent(self.strategy, fixed_lot=0.01)

        # Phase 1: IS learning
        sim_b_is = Simulator(agent_b, is_series, self.timeframe_str)
        sim_b_is.run()  # results discarded — we only care about learning

        # Phase 2: OOS evaluation (agent_b retains learned state)
        # Reset trade list for OOS counting, but keep memory/changepoint state
        agent_b.trades = []
        agent_b.dqs_log = []
        agent_b.changepoint_log = []
        agent_b.skipped_signals = 0
        sim_b_oos = Simulator(agent_b, oos_series, self.timeframe_str)
        result_b = sim_b_oos.run()

        return self._build_report(result_a, result_b)

    def ablation(self) -> List[AblationResult]:
        """Run 4 ablation variants — each removes one component.

        Variants:
        - no_dqs: CalibratedAgent but DQS always returns 'go'
        - no_changepoint: CalibratedAgent but ignores changepoint signals
        - no_kelly: CalibratedAgent but doesn't use Kelly sizing
        - no_regime: CalibratedAgent but ignores regime in DQS

        Returns list of AblationResult comparing each variant to full Agent B.
        """
        is_series, oos_series = self.series.split(self.is_ratio)
        results = []

        # First run full Agent B for baseline
        full_b = self._run_calibrated(is_series, oos_series)

        # Variant 1: no DQS (always go)
        no_dqs_b = self._run_calibrated_variant(
            is_series, oos_series, disable_dqs=True
        )
        results.append(AblationResult(
            variant_name="no_dqs",
            result=no_dqs_b,
            sharpe_delta=no_dqs_b.fitness.sharpe_ratio - full_b.fitness.sharpe_ratio,
        ))

        # Variant 2: no changepoint
        no_cp_b = self._run_calibrated_variant(
            is_series, oos_series, disable_changepoint=True
        )
        results.append(AblationResult(
            variant_name="no_changepoint",
            result=no_cp_b,
            sharpe_delta=no_cp_b.fitness.sharpe_ratio - full_b.fitness.sharpe_ratio,
        ))

        # Variant 3: no Kelly
        no_kelly_b = self._run_calibrated_variant(
            is_series, oos_series, disable_kelly=True
        )
        results.append(AblationResult(
            variant_name="no_kelly",
            result=no_kelly_b,
            sharpe_delta=no_kelly_b.fitness.sharpe_ratio - full_b.fitness.sharpe_ratio,
        ))

        # Variant 4: no regime filter
        no_regime_b = self._run_calibrated_variant(
            is_series, oos_series, disable_regime=True
        )
        results.append(AblationResult(
            variant_name="no_regime",
            result=no_regime_b,
            sharpe_delta=no_regime_b.fitness.sharpe_ratio - full_b.fitness.sharpe_ratio,
        ))

        return results

    def _run_calibrated(
        self, is_series: OHLCVSeries, oos_series: OHLCVSeries
    ) -> SimulationResult:
        """Run standard CalibratedAgent: IS learn → OOS evaluate."""
        agent = CalibratedAgent(self.strategy, fixed_lot=0.01)
        Simulator(agent, is_series, self.timeframe_str).run()
        agent.trades = []
        agent.dqs_log = []
        agent.changepoint_log = []
        agent.skipped_signals = 0
        return Simulator(agent, oos_series, self.timeframe_str).run()

    def _run_calibrated_variant(
        self,
        is_series: OHLCVSeries,
        oos_series: OHLCVSeries,
        disable_dqs: bool = False,
        disable_changepoint: bool = False,
        disable_kelly: bool = False,
        disable_regime: bool = False,
    ) -> SimulationResult:
        """Run CalibratedAgent variant with one component disabled."""
        agent = _AblationAgent(
            self.strategy,
            fixed_lot=0.01,
            disable_dqs=disable_dqs,
            disable_changepoint=disable_changepoint,
            disable_kelly=disable_kelly,
            disable_regime=disable_regime,
        )
        Simulator(agent, is_series, self.timeframe_str).run()
        agent.trades = []
        agent.dqs_log = []
        agent.changepoint_log = []
        agent.skipped_signals = 0
        return Simulator(agent, oos_series, self.timeframe_str).run()

    def _build_report(
        self, result_a: SimulationResult, result_b: SimulationResult
    ) -> ComparisonReport:
        """Build comparison report from A/B results."""
        sharpe_a = result_a.fitness.sharpe_ratio
        sharpe_b = result_b.fitness.sharpe_ratio
        sharpe_imp = (sharpe_b - sharpe_a) / max(abs(sharpe_a), 0.01)

        dd_a = result_a.fitness.max_drawdown_pct
        dd_b = result_b.fitness.max_drawdown_pct
        dd_red = (dd_a - dd_b) / max(dd_a, 0.01)

        # Find skipped trades: trades in A but not in B (by bar index)
        a_entries = {t.entry_bar_index for t in result_a.trades}
        b_entries = {t.entry_bar_index for t in result_b.trades}
        skipped_entries = a_entries - b_entries
        skipped_pnl = sum(
            t.pnl for t in result_a.trades if t.entry_bar_index in skipped_entries
        )

        # DQS-PnL correlation
        dqs_pnl_corr = _compute_dqs_pnl_correlation(result_b)

        # Statistical significance: simple paired t-test approximation
        stat_sig = _paired_significance(result_a.trades, result_b.trades)

        return ComparisonReport(
            agent_a=result_a,
            agent_b=result_b,
            sharpe_improvement=round(sharpe_imp, 4),
            dd_reduction=round(dd_red, 4),
            trades_skipped_by_b=result_b.skipped_signals,
            pnl_of_skipped_trades=round(skipped_pnl, 4),
            dqs_pnl_correlation=round(dqs_pnl_corr, 4),
            statistical_significance=stat_sig,
        )


class _AblationAgent(CalibratedAgent):
    """CalibratedAgent with individual components disabled for ablation."""

    def __init__(
        self,
        strategy: CandidatePattern,
        fixed_lot: float = 0.01,
        disable_dqs: bool = False,
        disable_changepoint: bool = False,
        disable_kelly: bool = False,
        disable_regime: bool = False,
    ):
        super().__init__(strategy, fixed_lot=fixed_lot)
        self._disable_dqs = disable_dqs
        self._disable_changepoint = disable_changepoint
        self._disable_kelly = disable_kelly
        self._disable_regime = disable_regime

    def should_trade(self, context):
        """Modified should_trade with ablation flags."""
        from tradememory.evolution.backtester import check_entry

        if not check_entry(self.strategy, context):
            return None

        from tradememory.simulation.agent import TradeSignal

        lot = self.fixed_lot

        # DQS gate (skip if disabled)
        if not self._disable_dqs:
            try:
                dqs = self.dqs_engine.compute(
                    symbol=context.symbol or "UNKNOWN",
                    strategy_name=self.strategy.name,
                    direction=self.strategy.entry_condition.direction,
                    proposed_lot_size=lot,
                    context_regime=(
                        None if self._disable_regime
                        else (context.regime.value if context.regime else None)
                    ),
                    context_atr_d1=context.atr_d1,
                )
                self._last_dqs_score = dqs.score
                self._last_dqs_tier = dqs.tier
                self.dqs_log.append({
                    "trade_index": self._trade_count,
                    "score": dqs.score,
                    "tier": dqs.tier,
                })
                if dqs.tier == "skip":
                    self.skipped_signals += 1
                    return None
                lot *= dqs.position_multiplier
            except Exception:
                pass
        else:
            self._last_dqs_score = 10.0
            self._last_dqs_tier = "go"

        # Changepoint (skip if disabled)
        if not self._disable_changepoint:
            if self._last_cp_prob > 0.5 or self._last_cusum_alert:
                lot *= 0.5

        # Kelly (skip if disabled)
        if not self._disable_kelly:
            try:
                procs = self.db.query_procedural(
                    strategy=self.strategy.name,
                    symbol=context.symbol or "UNKNOWN",
                    limit=1,
                )
                if procs:
                    kelly = procs[0].get("kelly_fraction_suggested")
                    if kelly and kelly > 0:
                        lot = min(lot, kelly)
            except Exception:
                pass

        if lot <= 0:
            self.skipped_signals += 1
            return None

        return TradeSignal(
            direction=self.strategy.entry_condition.direction,
            lot_size=lot,
            reason=f"Ablation variant",
        )


def _compute_dqs_pnl_correlation(result: SimulationResult) -> float:
    """Compute Pearson correlation between DQS score and trade PnL."""
    if not result.dqs_log or len(result.trades) < 3:
        return 0.0

    # Match DQS scores to trades
    dqs_scores = []
    pnls = []
    dqs_by_idx = {d["trade_index"]: d["score"] for d in result.dqs_log}

    for i, trade in enumerate(result.trades):
        if trade.dqs_score is not None:
            dqs_scores.append(trade.dqs_score)
            pnls.append(trade.pnl)

    if len(dqs_scores) < 3:
        return 0.0

    # Pearson r
    n = len(dqs_scores)
    mean_x = sum(dqs_scores) / n
    mean_y = sum(pnls) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(dqs_scores, pnls)) / n
    std_x = math.sqrt(sum((x - mean_x) ** 2 for x in dqs_scores) / n)
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in pnls) / n)

    if std_x == 0 or std_y == 0:
        return 0.0

    return cov / (std_x * std_y)


def _paired_significance(
    trades_a: List[SimulatedTrade], trades_b: List[SimulatedTrade]
) -> Dict[str, Any]:
    """Simple significance test comparing trade PnLs.

    Uses Welch's t-test approximation (no scipy).
    """
    pnls_a = [t.pnl for t in trades_a]
    pnls_b = [t.pnl for t in trades_b]

    if len(pnls_a) < 5 or len(pnls_b) < 5:
        return {"test": "welch_t", "significant": False, "reason": "insufficient_trades"}

    n_a, n_b = len(pnls_a), len(pnls_b)
    mean_a = sum(pnls_a) / n_a
    mean_b = sum(pnls_b) / n_b
    var_a = sum((x - mean_a) ** 2 for x in pnls_a) / (n_a - 1) if n_a > 1 else 0
    var_b = sum((x - mean_b) ** 2 for x in pnls_b) / (n_b - 1) if n_b > 1 else 0

    se = math.sqrt(var_a / n_a + var_b / n_b) if (var_a / n_a + var_b / n_b) > 0 else 0.001
    t_stat = (mean_b - mean_a) / se

    # Approximate p-value using normal distribution (good enough for large n)
    # |t| > 1.96 → p < 0.05
    return {
        "test": "welch_t",
        "t_statistic": round(t_stat, 4),
        "mean_pnl_a": round(mean_a, 4),
        "mean_pnl_b": round(mean_b, 4),
        "n_a": n_a,
        "n_b": n_b,
        "significant": abs(t_stat) > 1.96,
    }

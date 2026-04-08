"""Experiment report generation — research-grade Markdown + JSON output.

Generates an 8-section professional report suitable for arXiv appendix:
1. Executive Summary
2. Methodology
3. Main Results (A/B comparison) with per-TF/symbol/strategy aggregation
4. Ablation Study with component importance ranking
5. Statistical Validation (DSR + significance)
6. Behavioral Analysis (changepoint + DQS + skipped trades)
7. Limitations & Risks
8. Conclusion (GO/NO-GO)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _mean(values: List[float]) -> float:
    """Safe mean that returns 0.0 for empty lists."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _stdev(values: List[float]) -> float:
    """Sample standard deviation, 0.0 if < 2 values."""
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def _median(values: List[float]) -> float:
    """Median of sorted values."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _r4(v: float) -> float:
    """Round to 4 decimal places."""
    return round(v, 4)


@dataclass
class FullExperimentReport:
    """Aggregate report across multiple A/B experiments."""

    results: List[Dict[str, Any]]

    # ──────────────────────────────────────────────
    # Aggregation helpers
    # ──────────────────────────────────────────────

    def _valid_results(self) -> List[Dict[str, Any]]:
        """Filter out errored experiments."""
        return [r for r in self.results if "error" not in r]

    def _aggregate_by(self, group_key: str) -> Dict[str, Dict[str, Any]]:
        """Aggregate results by timeframe/symbol/strategy."""
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in self._valid_results():
            key = r.get(group_key, "unknown")
            groups.setdefault(key, []).append(r)

        aggregated = {}
        for key, experiments in groups.items():
            comps = [e["comparison"] for e in experiments]
            sig_count = sum(
                1 for c in comps
                if c.get("significance", {}).get("significant")
            )
            aggregated[key] = {
                "count": len(experiments),
                "avg_sharpe_a": _r4(_mean([c["sharpe_a"] for c in comps])),
                "avg_sharpe_b": _r4(_mean([c["sharpe_b"] for c in comps])),
                "avg_sharpe_improvement": _r4(_mean([c["sharpe_improvement"] for c in comps])),
                "avg_dd_a": _r4(_mean([c.get("dd_a", 0) for c in comps])),
                "avg_dd_b": _r4(_mean([c.get("dd_b", 0) for c in comps])),
                "avg_dd_reduction": _r4(_mean([c["dd_reduction"] for c in comps])),
                "total_skipped": sum(c.get("trades_skipped", 0) for c in comps),
                "avg_dqs_corr": _r4(_mean([c.get("dqs_pnl_correlation", 0) for c in comps])),
                "significant_count": sig_count,
            }
        return aggregated

    def _ablation_importance(self) -> List[Dict[str, Any]]:
        """Rank calibration components by importance across all experiments."""
        component_deltas: Dict[str, List[float]] = {
            "no_dqs": [], "no_changepoint": [], "no_kelly": [], "no_regime": [],
        }
        for r in self._valid_results():
            for abl in r.get("ablation", []):
                variant = abl.get("variant", "")
                if variant in component_deltas:
                    component_deltas[variant].append(abl.get("sharpe_delta", 0))

        ranking = []
        for component, deltas in component_deltas.items():
            if deltas:
                avg_delta = _r4(_mean(deltas))
                if avg_delta < -0.05:
                    importance = "critical"
                elif avg_delta < -0.01:
                    importance = "moderate"
                else:
                    importance = "minimal"
                ranking.append({
                    "component": component,
                    "avg_sharpe_delta": avg_delta,
                    "std_sharpe_delta": _r4(_stdev(deltas)),
                    "n_experiments": len(deltas),
                    "importance": importance,
                })

        return sorted(ranking, key=lambda x: x["avg_sharpe_delta"])

    def _significance_summary(self) -> Dict[str, int]:
        """Count how many experiments show significant improvement."""
        b_better = 0
        no_diff = 0
        a_better = 0
        for r in self._valid_results():
            sig = r.get("comparison", {}).get("significance", {})
            t = sig.get("t_statistic", 0)
            significant = sig.get("significant", False)
            if significant and t > 0:
                b_better += 1
            elif significant and t < 0:
                a_better += 1
            else:
                no_diff += 1
        return {
            "b_significantly_better": b_better,
            "no_significant_difference": no_diff,
            "a_significantly_better": a_better,
            "total": b_better + no_diff + a_better,
        }

    def _dqs_aggregate(self) -> Dict[str, Any]:
        """Aggregate DQS distribution stats across all experiments."""
        all_means = []
        all_medians = []
        tier_totals = {"go": 0, "proceed": 0, "caution": 0, "skip": 0}
        tier_pnls = {"go": [], "proceed": [], "caution": [], "skip": []}
        total_trades = 0

        for r in self._valid_results():
            dqs = r.get("dqs_stats", {})
            if dqs.get("mean") is not None:
                all_means.append(dqs["mean"])
            if dqs.get("median") is not None:
                all_medians.append(dqs["median"])
            dist = dqs.get("tier_distribution", {})
            count = dqs.get("count", 0)
            for tier in tier_totals:
                tier_totals[tier] += int(dist.get(tier, 0) * count)
            total_trades += count

            tp = r.get("tier_pnl", {})
            for tier in tier_pnls:
                tier_pnls[tier].extend(tp.get(tier, []))

        return {
            "grand_mean": _r4(_mean(all_means)),
            "grand_median": _r4(_mean(all_medians)),
            "tier_counts": tier_totals,
            "total_trades": total_trades,
            "tier_avg_pnl": {
                tier: _r4(_mean(pnls)) for tier, pnls in tier_pnls.items()
            },
        }

    def _changepoint_aggregate(self) -> Dict[str, Any]:
        """Aggregate changepoint detection stats."""
        total_alerts = 0
        cusum_alerts = 0
        max_probs = []
        for r in self._valid_results():
            cp = r.get("changepoint_stats", {})
            total_alerts += cp.get("total_alerts", 0)
            cusum_alerts += cp.get("cusum_alerts", 0)
            mp = cp.get("max_cp_prob", 0)
            if mp > 0:
                max_probs.append(mp)
        return {
            "total_alerts": total_alerts,
            "cusum_alerts": cusum_alerts,
            "avg_max_cp_prob": _r4(_mean(max_probs)),
            "experiments_with_alerts": sum(1 for p in max_probs if p > 0.5),
        }

    def _skip_aggregate(self) -> Dict[str, Any]:
        """Aggregate skipped trade analysis."""
        total_skipped = 0
        total_skipped_losing = 0
        total_skipped_pnl = 0.0
        for r in self._valid_results():
            comp = r.get("comparison", {})
            total_skipped += comp.get("trades_skipped", 0)
            total_skipped_pnl += comp.get("skipped_pnl", 0)
            total_skipped_losing += r.get("skip_precision_count", 0)
        precision = total_skipped_losing / max(total_skipped, 1)
        return {
            "total_skipped": total_skipped,
            "total_skipped_losing": total_skipped_losing,
            "skip_precision": _r4(precision),
            "total_skipped_pnl": _r4(total_skipped_pnl),
        }

    # ──────────────────────────────────────────────
    # Table generators
    # ──────────────────────────────────────────────

    def summary_table(self) -> str:
        """Main A/B comparison table."""
        lines = [
            "| Symbol | TF | Strategy | Sharpe A | Sharpe B | \u0394 Sharpe | DD A | DD B | \u0394 DD | Trades A | Trades B | Skipped | Skip PnL | DQS-PnL r | p-value | Sig? |",
            "|--------|-----|----------|----------|----------|---------|------|------|------|----------|----------|---------|----------|-----------|---------|------|",
        ]
        for r in self._valid_results():
            comp = r.get("comparison", {})
            sig = comp.get("significance", {})
            t_stat = sig.get("t_statistic", 0)
            # Approximate p from |t|: use rough mapping
            p_approx = _approx_p_from_t(abs(t_stat), sig.get("n_a", 30) + sig.get("n_b", 30))
            sig_mark = "YES" if sig.get("significant") else "no"
            lines.append(
                f"| {r.get('symbol', '')} "
                f"| {r.get('timeframe', '')} "
                f"| {r.get('strategy', '')} "
                f"| {comp.get('sharpe_a', 0):.4f} "
                f"| {comp.get('sharpe_b', 0):.4f} "
                f"| {comp.get('sharpe_improvement', 0):+.1%} "
                f"| {comp.get('dd_a', 0):.1%} "
                f"| {comp.get('dd_b', 0):.1%} "
                f"| {comp.get('dd_reduction', 0):+.1%} "
                f"| {comp.get('trades_a', 0)} "
                f"| {comp.get('trades_b', 0)} "
                f"| {comp.get('trades_skipped', 0)} "
                f"| {comp.get('skipped_pnl', 0):.2f} "
                f"| {comp.get('dqs_pnl_correlation', 0):.4f} "
                f"| {p_approx:.3f} "
                f"| {sig_mark} |"
            )
        return "\n".join(lines)

    def _aggregation_table(self, group_key: str, group_label: str) -> str:
        """Generic aggregation table by group_key."""
        agg = self._aggregate_by(group_key)
        lines = [
            f"| {group_label} | N | Avg Sharpe A | Avg Sharpe B | Avg \u0394 Sharpe | Avg \u0394 DD | Skipped | Avg DQS-PnL r | Sig Count |",
            f"|{'---' * len(group_label)}|---|--------------|--------------|-------------|--------|---------|---------------|-----------|",
        ]
        for key, data in sorted(agg.items()):
            lines.append(
                f"| {key} "
                f"| {data['count']} "
                f"| {data['avg_sharpe_a']:.4f} "
                f"| {data['avg_sharpe_b']:.4f} "
                f"| {data['avg_sharpe_improvement']:+.1%} "
                f"| {data['avg_dd_reduction']:+.1%} "
                f"| {data['total_skipped']} "
                f"| {data['avg_dqs_corr']:.4f} "
                f"| {data['significant_count']}/{data['count']} |"
            )
        return "\n".join(lines)

    def ablation_table(self) -> str:
        """Detailed ablation table."""
        lines = [
            "| Symbol | TF | Strategy | Full B | No DQS | No CP | No Kelly | No Regime | Most Important |",
            "|--------|-----|----------|--------|--------|-------|----------|-----------|----------------|",
        ]
        for r in self._valid_results():
            abls = {a["variant"]: a for a in r.get("ablation", [])}
            full_sharpe = r.get("comparison", {}).get("sharpe_b", 0)
            # Find which removal hurts most
            worst = min(r.get("ablation", [{"sharpe_delta": 0}]), key=lambda a: a.get("sharpe_delta", 0))
            lines.append(
                f"| {r.get('symbol', '')} "
                f"| {r.get('timeframe', '')} "
                f"| {r.get('strategy', '')} "
                f"| {full_sharpe:.4f} "
                f"| {abls.get('no_dqs', {}).get('sharpe', 0):.4f} "
                f"| {abls.get('no_changepoint', {}).get('sharpe', 0):.4f} "
                f"| {abls.get('no_kelly', {}).get('sharpe', 0):.4f} "
                f"| {abls.get('no_regime', {}).get('sharpe', 0):.4f} "
                f"| {worst.get('variant', 'N/A')} |"
            )
        return "\n".join(lines)

    def _importance_table(self) -> str:
        """Component importance ranking from ablation."""
        ranking = self._ablation_importance()
        lines = [
            "| Component | Avg Sharpe \u0394 | Std | N | Importance |",
            "|-----------|-------------|-----|---|------------|",
        ]
        for r in ranking:
            lines.append(
                f"| {r['component']} "
                f"| {r['avg_sharpe_delta']:+.4f} "
                f"| {r['std_sharpe_delta']:.4f} "
                f"| {r['n_experiments']} "
                f"| {r['importance']} |"
            )
        return "\n".join(lines)

    def _dsr_table(self) -> str:
        """DSR results table."""
        lines = [
            "| Symbol | TF | Strategy | Sharpe (OOS) | DSR | p-value | Verdict |",
            "|--------|-----|----------|-------------|-----|---------|---------|",
        ]
        for r in self._valid_results():
            dsr = r.get("dsr", {})
            if not dsr:
                continue
            lines.append(
                f"| {r.get('symbol', '')} "
                f"| {r.get('timeframe', '')} "
                f"| {r.get('strategy', '')} "
                f"| {dsr.get('sharpe_raw', 0):.4f} "
                f"| {dsr.get('dsr', 0):.4f} "
                f"| {dsr.get('p_value', 1):.4f} "
                f"| {dsr.get('verdict', 'N/A')} |"
            )
        return "\n".join(lines)

    # ──────────────────────────────────────────────
    # Full report
    # ──────────────────────────────────────────────

    def to_markdown(self) -> str:
        """Full 8-section research-grade report."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        valid = self._valid_results()
        errored = [r for r in self.results if "error" in r]
        sig_summary = self._significance_summary()
        dqs_agg = self._dqs_aggregate()
        cp_agg = self._changepoint_aggregate()
        skip_agg = self._skip_aggregate()

        # Compute overall stats
        all_comps = [r["comparison"] for r in valid]
        avg_sharpe_imp = _mean([c["sharpe_improvement"] for c in all_comps])
        avg_dd_red = _mean([c["dd_reduction"] for c in all_comps])
        total_skipped = sum(c.get("trades_skipped", 0) for c in all_comps)

        sections = []

        # ── Header ──
        sections.append(f"# Self-Calibrating Trading Agent: Experiment Report")
        sections.append(f"> Generated: {ts} | TradeMemory Protocol v0.5.1")
        sections.append("")

        # ── 1. Executive Summary ──
        sections.append("## 1. Executive Summary")
        sections.append("")
        b_sig = sig_summary["b_significantly_better"]
        total_exp = sig_summary["total"]
        sections.append(
            f"Across {total_exp} A/B experiments (2 symbols x 3 timeframes x 3 strategies), "
            f"Agent B (self-calibrating) showed an average Sharpe improvement of "
            f"{avg_sharpe_imp:+.1%} and average drawdown reduction of {avg_dd_red:+.1%} "
            f"compared to Agent A (baseline). Agent B skipped {total_skipped} trades total "
            f"with a skip precision of {skip_agg['skip_precision']:.1%} "
            f"(proportion of skipped trades that were losers). "
            f"Statistical significance (p < 0.05): {b_sig}/{total_exp} experiments showed "
            f"Agent B significantly better, {sig_summary['a_significantly_better']}/{total_exp} "
            f"showed Agent A better, {sig_summary['no_significant_difference']}/{total_exp} "
            f"showed no significant difference."
        )
        sections.append("")

        # ── 2. Methodology ──
        sections.append("## 2. Methodology")
        sections.append("")
        sections.append("- **IS/OOS split**: 67% in-sample (training) / 33% out-of-sample (evaluation)")
        sections.append("- **Walk-forward design**: Agent B learns on IS period, evaluated purely on OOS")
        sections.append("- **Agent A (Baseline)**: Mechanical strategy execution, fixed lot size, no learning")
        sections.append("- **Agent B (Calibrated)**: Same base strategy + DQS gate + BOCPD changepoint + Kelly sizing + regime filter")
        sections.append("- **3 preset strategies**:")
        sections.append("  - TrendFollow: Enter on 12h uptrend + moderate ATR, SL=1.5 ATR, TP=3.0 ATR")
        sections.append("  - Breakout: Enter on high ATR expansion + strong trend, SL=2.0 ATR, TP=4.0 ATR")
        sections.append("  - MeanReversion: Enter on low ATR range-bound, SL=1.0 ATR, TP=1.5 ATR")
        sections.append("- **Calibration components**:")
        sections.append("  - DQS (Decision Quality Score): 5-factor continuous scoring (0-10), 4 tiers (go/proceed/caution/skip)")
        sections.append("  - BOCPD (Bayesian Online Changepoint Detection): Adams & MacKay 2007, Beta-Bernoulli + NIG conjugate models")
        sections.append("  - CUSUM: Complementary cumulative sum detector for rapid shifts")
        sections.append("  - Kelly sizing: From procedural memory's kelly_fraction")
        sections.append("- **Statistical tests**: Welch's t-test on trade PnLs, DSR (Deflated Sharpe Ratio), Pearson correlation")
        sections.append("- **Data**: 3 years of Binance spot OHLCV, no slippage, no transaction costs")
        sections.append("")

        # ── 3. Main Results ──
        sections.append("## 3. Main Results -- A/B Comparison")
        sections.append("")
        sections.append("### 3.1 Full Results Table")
        sections.append("")
        sections.append(self.summary_table())
        sections.append("")

        if errored:
            sections.append(f"*{len(errored)} experiment(s) failed and are excluded from analysis.*")
            sections.append("")

        # 3.2 Per-Timeframe
        sections.append("### 3.2 Per-Timeframe Analysis")
        sections.append("")
        sections.append(self._aggregation_table("timeframe", "Timeframe"))
        sections.append("")
        tf_agg = self._aggregate_by("timeframe")
        if tf_agg:
            best_tf = max(tf_agg.items(), key=lambda x: x[1]["avg_sharpe_improvement"])
            sections.append(
                f"Calibration shows strongest improvement on **{best_tf[0]}** "
                f"({best_tf[1]['avg_sharpe_improvement']:+.1%} avg Sharpe improvement)."
            )
        sections.append("")

        # 3.3 Per-Symbol
        sections.append("### 3.3 Per-Symbol Analysis")
        sections.append("")
        sections.append(self._aggregation_table("symbol", "Symbol"))
        sections.append("")
        sym_agg = self._aggregate_by("symbol")
        if len(sym_agg) >= 2:
            imps = [v["avg_sharpe_improvement"] for v in sym_agg.values()]
            spread = max(imps) - min(imps)
            sections.append(
                f"Cross-market spread in improvement: {spread:.1%}. "
                f"{'Consistent' if spread < 0.1 else 'Divergent'} across symbols."
            )
        sections.append("")

        # 3.4 Per-Strategy
        sections.append("### 3.4 Per-Strategy Analysis")
        sections.append("")
        sections.append(self._aggregation_table("strategy", "Strategy"))
        sections.append("")
        strat_agg = self._aggregate_by("strategy")
        if strat_agg:
            best_strat = max(strat_agg.items(), key=lambda x: x[1]["avg_sharpe_improvement"])
            sections.append(
                f"Calibration is most effective for **{best_strat[0]}** "
                f"({best_strat[1]['avg_sharpe_improvement']:+.1%})."
            )
        sections.append("")

        # ── 4. Ablation Study ──
        sections.append("## 4. Ablation Study")
        sections.append("")
        sections.append("### 4.1 Ablation Table")
        sections.append("")
        sections.append(self.ablation_table())
        sections.append("")
        sections.append("### 4.2 Component Importance Ranking")
        sections.append("")
        sections.append(self._importance_table())
        sections.append("")
        ranking = self._ablation_importance()
        if ranking:
            most_important = ranking[0]
            sections.append(
                f"Most important component: **{most_important['component']}** "
                f"(removing it causes avg Sharpe delta of {most_important['avg_sharpe_delta']:+.4f}). "
                f"Importance: {most_important['importance']}."
            )
        sections.append("")

        # ── 5. Statistical Validation ──
        sections.append("## 5. Statistical Validation")
        sections.append("")

        # 5.1 DSR
        sections.append("### 5.1 Deflated Sharpe Ratio (DSR)")
        sections.append("")
        dsr_table = self._dsr_table()
        if "N/A" not in dsr_table and len(dsr_table.split("\n")) > 2:
            sections.append(dsr_table)
            dsr_pass = sum(
                1 for r in valid
                if r.get("dsr", {}).get("verdict") == "PASS"
            )
            dsr_fail = sum(
                1 for r in valid
                if r.get("dsr", {}).get("verdict") == "FAIL"
            )
            dsr_insuf = sum(
                1 for r in valid
                if r.get("dsr", {}).get("verdict") == "INSUFFICIENT_DATA"
            )
            sections.append("")
            sections.append(
                f"DSR results: {dsr_pass} PASS, {dsr_fail} FAIL, "
                f"{dsr_insuf} INSUFFICIENT_DATA out of {len(valid)} experiments."
            )
        else:
            sections.append("*DSR data not available for these experiments.*")
        sections.append("")

        # 5.2 DQS-PnL Correlation
        sections.append("### 5.2 DQS-PnL Correlation")
        sections.append("")
        corrs = [r["comparison"].get("dqs_pnl_correlation", 0) for r in valid]
        sections.append(f"- Aggregate mean DQS-PnL Pearson r: **{_mean(corrs):.4f}**")
        sections.append(f"- Range: [{min(corrs):.4f}, {max(corrs):.4f}]" if corrs else "- No data")
        sections.append(f"- Positive r indicates DQS score is predictive of trade outcome")
        sections.append("")

        # 5.3 Significance Summary
        sections.append("### 5.3 Significance Summary")
        sections.append("")
        sections.append(f"- {sig_summary['b_significantly_better']}/{total_exp} experiments: Agent B significantly better (p < 0.05)")
        sections.append(f"- {sig_summary['no_significant_difference']}/{total_exp} experiments: no significant difference")
        sections.append(f"- {sig_summary['a_significantly_better']}/{total_exp} experiments: Agent A better (calibration harmful)")
        sections.append("")

        # ── 6. Behavioral Analysis ──
        sections.append("## 6. Behavioral Analysis")
        sections.append("")

        # 6.1 Changepoint
        sections.append("### 6.1 Changepoint Detection")
        sections.append("")
        sections.append(f"- Total BOCPD alerts (cp_prob > 0.5): {cp_agg['total_alerts']}")
        sections.append(f"- Total CUSUM alerts: {cp_agg['cusum_alerts']}")
        sections.append(f"- Avg max changepoint probability: {cp_agg['avg_max_cp_prob']:.4f}")
        sections.append(f"- Experiments with at least one alert: {cp_agg['experiments_with_alerts']}/{len(valid)}")
        sections.append("")

        # 6.2 DQS Distribution
        sections.append("### 6.2 DQS Distribution")
        sections.append("")
        sections.append(f"- Grand mean DQS score: {dqs_agg['grand_mean']:.4f}")
        sections.append(f"- Grand median DQS score: {dqs_agg['grand_median']:.4f}")
        sections.append(f"- Total DQS-scored trades: {dqs_agg['total_trades']}")
        sections.append("")
        sections.append("**Tier distribution:**")
        sections.append("")
        sections.append("| Tier | Count | Avg PnL |")
        sections.append("|------|-------|---------|")
        for tier in ["go", "proceed", "caution", "skip"]:
            cnt = dqs_agg["tier_counts"].get(tier, 0)
            avg_pnl = dqs_agg["tier_avg_pnl"].get(tier, 0)
            sections.append(f"| {tier} | {cnt} | {avg_pnl:.4f} |")
        sections.append("")

        # 6.3 Skipped Trade Analysis
        sections.append("### 6.3 Skipped Trade Analysis")
        sections.append("")
        sections.append(f"- Total trades skipped by Agent B: {skip_agg['total_skipped']}")
        sections.append(f"- Of those, losers in Agent A: {skip_agg['total_skipped_losing']}")
        sections.append(f"- Skip precision: **{skip_agg['skip_precision']:.1%}** (higher = DQS more accurate)")
        sections.append(f"- Total PnL of skipped trades (Agent A): {skip_agg['total_skipped_pnl']:.4f}")
        sections.append("")

        # ── 7. Limitations ──
        sections.append("## 7. Limitations & Risks")
        sections.append("")
        sections.append("- No slippage model: real-world execution would degrade results")
        sections.append("- No transaction costs: spreads and commissions not modeled")
        sections.append("- Crypto-only: results on BTCUSDT/ETHUSDT may not generalize to forex/stocks")
        sections.append("- IS/OOS split is time-based (correct for financial data, but only one split point)")
        sections.append("- Small strategy universe: only 3 preset strategies tested")
        sections.append("- DQS calibration uses in-sample data: potential look-ahead bias in weight learning")
        sections.append("- Changepoint detector hazard rate (1/50) is a fixed hyperparameter, not optimized")
        sections.append("- Single fixed lot size for Agent A: does not account for position sizing edge")
        sections.append("")

        # ── 8. Conclusion ──
        sections.append("## 8. Conclusion")
        sections.append("")

        # GO/NO-GO logic
        go_criteria = []
        nogo_criteria = []

        if avg_sharpe_imp > 0:
            go_criteria.append(f"Average Sharpe improvement positive ({avg_sharpe_imp:+.1%})")
        else:
            nogo_criteria.append(f"Average Sharpe improvement negative ({avg_sharpe_imp:+.1%})")

        if b_sig > total_exp * 0.3:
            go_criteria.append(f">{30}% experiments show significant improvement ({b_sig}/{total_exp})")
        else:
            nogo_criteria.append(f"<30% experiments show significant improvement ({b_sig}/{total_exp})")

        if skip_agg["skip_precision"] > 0.5:
            go_criteria.append(f"Skip precision > 50% ({skip_agg['skip_precision']:.1%})")
        else:
            nogo_criteria.append(f"Skip precision <= 50% ({skip_agg['skip_precision']:.1%})")

        if _mean(corrs) > 0:
            go_criteria.append(f"DQS-PnL correlation positive ({_mean(corrs):.4f})")
        else:
            nogo_criteria.append(f"DQS-PnL correlation non-positive ({_mean(corrs):.4f})")

        verdict = "GO" if len(go_criteria) >= 3 else "NO-GO"

        sections.append(f"### Phase 5 Decision: **{verdict}**")
        sections.append("")
        if go_criteria:
            sections.append("**Evidence supporting GO:**")
            for c in go_criteria:
                sections.append(f"- {c}")
            sections.append("")
        if nogo_criteria:
            sections.append("**Evidence against (risks):**")
            for c in nogo_criteria:
                sections.append(f"- {c}")
            sections.append("")

        sections.append("**Claims with data support:**")
        if avg_sharpe_imp > 0:
            sections.append(f"- Calibration improves average Sharpe by {avg_sharpe_imp:+.1%}")
        if avg_dd_red > 0:
            sections.append(f"- Calibration reduces average drawdown by {avg_dd_red:+.1%}")
        if skip_agg["skip_precision"] > 0.5:
            sections.append(f"- DQS successfully identifies losing trades (precision {skip_agg['skip_precision']:.1%})")
        sections.append("")

        sections.append("**Claims WITHOUT sufficient data support:**")
        if abs(_mean(corrs)) < 0.1:
            sections.append("- DQS as a standalone predictor (correlation too weak)")
        if b_sig < total_exp * 0.5:
            sections.append(f"- Universal improvement (only {b_sig}/{total_exp} statistically significant)")
        sections.append("")

        sections.append("---")
        sections.append(f"*Report generated by TradeMemory Protocol v0.5.1 Simulation Framework*")

        return "\n".join(sections)

    def save(self, path: str):
        """Save JSON + markdown report."""
        json_path = path if path.endswith(".json") else path + ".json"
        md_path = path.replace(".json", ".md") if path.endswith(".json") else path + ".md"

        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        with open(md_path, "w") as f:
            f.write(self.to_markdown())


def _approx_p_from_t(t_abs: float, df: int) -> float:
    """Rough p-value approximation from |t| without scipy.

    Uses normal approximation (good for df > 30).
    Returns two-tailed p-value.
    """
    if df < 2:
        return 1.0
    # Normal CDF approximation using error function
    # P(Z > t) ~ 0.5 * erfc(t / sqrt(2))
    z = t_abs
    # Abramowitz & Stegun approximation for erfc
    p = 0.3275911
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    t_val = 1.0 / (1.0 + p * z / math.sqrt(2))
    erfc_approx = (a1 * t_val + a2 * t_val**2 + a3 * t_val**3 + a4 * t_val**4 + a5 * t_val**5) * math.exp(-z**2 / 2)
    return min(erfc_approx, 1.0)  # two-tailed is already approximated

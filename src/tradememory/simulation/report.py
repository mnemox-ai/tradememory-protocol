"""Experiment report generation — Markdown tables + JSON output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class FullExperimentReport:
    """Aggregate report across multiple A/B experiments."""

    results: List[Dict[str, Any]]

    def summary_table(self) -> str:
        """Markdown table: symbol x timeframe x strategy → Sharpe A, Sharpe B, improvement."""
        lines = [
            "| Symbol | Timeframe | Strategy | Sharpe A | Sharpe B | Improvement | DD Reduction | Skipped | Skipped PnL |",
            "|--------|-----------|----------|----------|----------|-------------|--------------|---------|-------------|",
        ]
        for r in self.results:
            comp = r.get("comparison", {})
            lines.append(
                f"| {r.get('symbol', '')} "
                f"| {r.get('timeframe', '')} "
                f"| {r.get('strategy', '')} "
                f"| {comp.get('sharpe_a', 0):.4f} "
                f"| {comp.get('sharpe_b', 0):.4f} "
                f"| {comp.get('sharpe_improvement', 0):+.1%} "
                f"| {comp.get('dd_reduction', 0):+.1%} "
                f"| {comp.get('trades_skipped', 0)} "
                f"| {comp.get('skipped_pnl', 0):.2f} |"
            )
        return "\n".join(lines)

    def ablation_table(self) -> str:
        """Markdown table: component removed → impact on Sharpe."""
        lines = [
            "| Symbol | Timeframe | Strategy | Component Removed | Sharpe (variant) | Sharpe Delta | Impact |",
            "|--------|-----------|----------|-------------------|------------------|--------------|--------|",
        ]
        for r in self.results:
            for abl in r.get("ablation", []):
                delta = abl.get("sharpe_delta", 0)
                impact = "helpful" if delta < -0.01 else ("neutral" if abs(delta) < 0.01 else "harmful")
                lines.append(
                    f"| {r.get('symbol', '')} "
                    f"| {r.get('timeframe', '')} "
                    f"| {r.get('strategy', '')} "
                    f"| {abl.get('variant', '')} "
                    f"| {abl.get('sharpe', 0):.4f} "
                    f"| {delta:+.4f} "
                    f"| {impact} |"
                )
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Full report with all tables."""
        sections = [
            "# Phase 3: Agent Simulation — Experiment Results",
            "",
            "## A/B Comparison: BaseAgent vs CalibratedAgent",
            "",
            self.summary_table(),
            "",
            "## Ablation Study: Component Impact",
            "",
            self.ablation_table(),
            "",
            "## Methodology",
            "",
            "- **IS/OOS split**: 67% in-sample (training) / 33% out-of-sample (evaluation)",
            "- **Agent A (Baseline)**: Mechanical execution of strategy rules",
            "- **Agent B (Calibrated)**: Same rules + DQS gate + changepoint detection + Kelly sizing",
            "- **Ablation**: Remove one component at a time to measure individual contribution",
            "",
        ]
        return "\n".join(sections)

    def save(self, path: str):
        """Save JSON + markdown report."""
        json_path = path if path.endswith(".json") else path + ".json"
        md_path = path.replace(".json", ".md") if path.endswith(".json") else path + ".md"

        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        with open(md_path, "w") as f:
            f.write(self.to_markdown())

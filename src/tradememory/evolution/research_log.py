"""Research log auto-writer for Evolution Engine.

Writes structured markdown experiment logs in EXP-00X format
from EvolutionRun results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tradememory.evolution.models import EvolutionRun, Hypothesis, HypothesisStatus


def _next_experiment_id(log_path: str) -> str:
    """Scan existing log file and return next EXP-XXX id."""
    path = Path(log_path)
    if not path.exists():
        return "EXP-001"

    max_id = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## EXP-"):
            try:
                num = int(line.split("EXP-")[1].split(":")[0].strip())
                max_id = max(max_id, num)
            except (ValueError, IndexError):
                continue
    return f"EXP-{max_id + 1:03d}"


def _format_fitness_row(h: Hypothesis) -> str:
    """Format a single hypothesis as a markdown table row."""
    name = h.pattern.name
    gen = h.generation
    status = h.status.value

    is_sharpe = f"{h.fitness_is.sharpe_ratio:.2f}" if h.fitness_is else "—"
    is_wr = f"{h.fitness_is.win_rate * 100:.1f}%" if h.fitness_is else "—"
    is_trades = str(h.fitness_is.trade_count) if h.fitness_is else "—"

    oos_sharpe = f"{h.fitness_oos.sharpe_ratio:.2f}" if h.fitness_oos else "—"
    oos_wr = f"{h.fitness_oos.win_rate * 100:.1f}%" if h.fitness_oos else "—"

    reason = h.elimination_reason or ""

    return f"| {name} | {gen} | {status} | {is_sharpe} | {is_wr} | {is_trades} | {oos_sharpe} | {oos_wr} | {reason} |"


def format_experiment_log(run: EvolutionRun, experiment_id: Optional[str] = None) -> str:
    """Format an EvolutionRun as a structured markdown experiment log.

    Args:
        run: Completed EvolutionRun.
        experiment_id: Override experiment ID (auto-detected if None).

    Returns:
        Markdown string for the experiment entry.
    """
    exp_id = experiment_id or "EXP-001"
    date = run.completed_at or run.started_at
    date_str = date.strftime("%Y-%m-%d %H:%M UTC") if date else "unknown"

    lines = [
        f"## {exp_id}: {run.config.symbol} {run.config.timeframe} — {run.config.generations} generations",
        "",
        f"- **Date**: {date_str}",
        f"- **Run ID**: {run.run_id}",
        f"- **Symbol**: {run.config.symbol}",
        f"- **Timeframe**: {run.config.timeframe}",
        f"- **Generations**: {run.config.generations}",
        f"- **Population**: {run.config.population_size}",
        f"- **IS/OOS Split**: {run.config.is_oos_ratio:.0%} / {1 - run.config.is_oos_ratio:.0%}",
        f"- **LLM Tokens**: {run.total_llm_tokens:,}",
        f"- **Backtests**: {run.total_backtests}",
        "",
        "### Results",
        "",
        "| Strategy | Gen | Status | Sharpe IS | WR IS | Trades IS | Sharpe OOS | WR OOS | Elimination |",
        "|----------|-----|--------|-----------|-------|-----------|------------|--------|-------------|",
    ]

    # Graduated first
    for h in run.graduated:
        lines.append(_format_fitness_row(h))

    # Then graveyard
    for h in run.graveyard:
        lines.append(_format_fitness_row(h))

    # Summary
    lines.extend([
        "",
        "### Graveyard Summary",
        "",
        f"- **Graduated**: {len(run.graduated)}",
        f"- **Eliminated**: {len(run.graveyard)}",
    ])

    if run.graveyard:
        reasons: dict[str, int] = {}
        for h in run.graveyard:
            reason = h.elimination_reason or "unknown"
            # Bucket by first word pattern
            key = reason.split("—")[0].strip() if "—" in reason else reason
            reasons[key] = reasons.get(key, 0) + 1

        lines.append("- **Elimination reasons**:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            lines.append(f"  - {reason}: {count}")

    lines.extend(["", "---", ""])

    return "\n".join(lines)


def write_experiment_log(run: EvolutionRun, log_path: str) -> str:
    """Append a structured experiment entry to the research log file.

    Args:
        run: Completed EvolutionRun.
        log_path: Path to the markdown log file.

    Returns:
        The experiment ID that was written.
    """
    path = Path(log_path)
    exp_id = _next_experiment_id(log_path)

    entry = format_experiment_log(run, experiment_id=exp_id)

    # Create file with header if it doesn't exist
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        header = "# Evolution Research Log\n\n"
        path.write_text(header + entry, encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(entry)

    return exp_id

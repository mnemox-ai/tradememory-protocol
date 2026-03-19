#!/usr/bin/env python3
"""B1: L2 Discovery Engine Stability Test.

Question: Is the LLM pattern discovery deterministic enough to be reliable?
Method: Same BTCUSDT data → discover_patterns() 4 times:
  - Run 0: temperature=0.0 (deterministic control)
  - Run 1-3: temperature=0.7 (default, measures LLM randomness)

Outputs:
  validation/b1_run0_control.json
  validation/b1_run1_patterns.json
  validation/b1_run2_patterns.json
  validation/b1_run3_patterns.json
  validation/b1_stability_report.md

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/run_b1_stability.py
"""

import asyncio
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.models import OHLCVSeries, Timeframe
from tradememory.evolution.discovery import discover_patterns
from tradememory.evolution.llm import AnthropicClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VALIDATION_DIR = Path(__file__).parent.parent / "validation"
VALIDATION_DIR.mkdir(exist_ok=True)


def pattern_to_dict(p) -> dict:
    """Convert CandidatePattern to serializable dict."""
    return {
        "name": p.name,
        "description": p.description,
        "direction": p.entry_condition.direction,
        "entry_conditions": [
            {"field": c.field, "op": c.op, "value": c.value}
            for c in p.entry_condition.conditions
        ],
        "exit": {
            "sl_atr": p.exit_condition.stop_loss_atr,
            "tp_atr": p.exit_condition.take_profit_atr,
            "max_bars": p.exit_condition.max_holding_bars,
            "trailing_atr": p.exit_condition.trailing_stop_atr,
        },
        "validity": {
            "regime": p.validity_conditions.regime if p.validity_conditions else None,
            "session": p.validity_conditions.session if p.validity_conditions else None,
        },
        "confidence": p.confidence,
        "sample_count": p.sample_count,
    }


async def fetch_data() -> OHLCVSeries:
    """Fetch BTCUSDT 1H data (uses parquet cache if available)."""
    ds = BinanceDataSource()
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 3, 17, tzinfo=timezone.utc)
    logger.info(f"Fetching BTCUSDT 1H {start.date()} to {end.date()}...")
    series = await ds.fetch_ohlcv("BTCUSDT", Timeframe.H1, start, end)
    logger.info(f"Got {len(series.bars)} bars")
    return series


async def run_discovery(
    llm: AnthropicClient,
    series: OHLCVSeries,
    temperature: float,
    run_id: str,
    count: int = 5,
) -> list[dict]:
    """Run discover_patterns once and return serialized results."""
    logger.info(f"=== {run_id}: temperature={temperature} ===")
    t0 = time.time()

    patterns, response = await discover_patterns(
        llm=llm,
        series=series,
        count=count,
        temperature=temperature,
    )

    elapsed = time.time() - t0
    tokens = response.input_tokens + response.output_tokens

    result = {
        "run_id": run_id,
        "temperature": temperature,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "tokens_used": tokens,
        "patterns_requested": count,
        "patterns_returned": len(patterns),
        "patterns": [pattern_to_dict(p) for p in patterns],
    }

    logger.info(
        f"  {run_id}: {len(patterns)}/{count} patterns, "
        f"{tokens} tokens, {elapsed:.1f}s"
    )
    return result


def compute_stability(runs: list[dict]) -> dict:
    """Compare patterns across runs. Returns stability metrics."""
    # Extract key features for each pattern
    def pattern_fingerprint(p: dict) -> str:
        """Create a simplified fingerprint: direction + key conditions."""
        direction = p["direction"]
        conditions = sorted(
            f"{c['field']}_{c['op']}_{c['value']}" for c in p["entry_conditions"]
        )
        return f"{direction}|{'|'.join(conditions)}"

    def pattern_theme(p: dict) -> str:
        """Extract high-level theme: direction + primary field."""
        direction = p["direction"]
        fields = sorted(set(c["field"] for c in p["entry_conditions"]))
        return f"{direction}|{'+'.join(fields)}"

    # Collect all fingerprints and themes per run
    run_fingerprints = []
    run_themes = []
    for run in runs:
        fps = set(pattern_fingerprint(p) for p in run["patterns"])
        themes = set(pattern_theme(p) for p in run["patterns"])
        run_fingerprints.append(fps)
        run_themes.append(themes)

    # Exact match: how many fingerprints appear in ALL runs?
    if run_fingerprints:
        common_exact = run_fingerprints[0]
        for fps in run_fingerprints[1:]:
            common_exact = common_exact & fps
        all_exact = set()
        for fps in run_fingerprints:
            all_exact = all_exact | fps
    else:
        common_exact = set()
        all_exact = set()

    # Theme match: how many themes appear in ALL runs?
    if run_themes:
        common_themes = run_themes[0]
        for ts in run_themes[1:]:
            common_themes = common_themes & ts
        all_themes = set()
        for ts in run_themes:
            all_themes = all_themes | ts
    else:
        common_themes = set()
        all_themes = set()

    # Direction consistency
    direction_counts = defaultdict(int)
    total_patterns = 0
    for run in runs:
        for p in run["patterns"]:
            direction_counts[p["direction"]] += 1
            total_patterns += 1

    # Hour condition consistency (most common condition type)
    hour_values = defaultdict(int)
    for run in runs:
        for p in run["patterns"]:
            for c in p["entry_conditions"]:
                if c["field"] == "hour_utc":
                    val = c["value"]
                    key = str(val) if isinstance(val, list) else val
                    hour_values[key] += 1

    # SL/TP consistency
    sl_values = []
    tp_values = []
    for run in runs:
        for p in run["patterns"]:
            if p["exit"]["sl_atr"]:
                sl_values.append(p["exit"]["sl_atr"])
            if p["exit"]["tp_atr"]:
                tp_values.append(p["exit"]["tp_atr"])

    return {
        "exact_match": {
            "common_across_all": len(common_exact),
            "total_unique": len(all_exact),
            "overlap_pct": round(len(common_exact) / max(len(all_exact), 1) * 100, 1),
        },
        "theme_match": {
            "common_across_all": len(common_themes),
            "total_unique": len(all_themes),
            "overlap_pct": round(len(common_themes) / max(len(all_themes), 1) * 100, 1),
            "common_list": sorted(common_themes),
        },
        "direction_distribution": dict(direction_counts),
        "total_patterns": total_patterns,
        "hour_distribution": dict(sorted(hour_values.items(), key=lambda x: -x[1])),
        "exit_stats": {
            "sl_atr_range": [min(sl_values, default=0), max(sl_values, default=0)],
            "tp_atr_range": [min(tp_values, default=0), max(tp_values, default=0)],
            "sl_atr_mean": round(sum(sl_values) / max(len(sl_values), 1), 2),
            "tp_atr_mean": round(sum(tp_values) / max(len(tp_values), 1), 2),
        },
    }


def generate_report(
    control: dict, normal_runs: list[dict], stability: dict
) -> str:
    """Generate the B1 stability report in markdown."""
    # Control vs normal comparison
    ctrl_stability = compute_stability([control])
    normal_stability = stability

    report = f"""# B1: L2 Discovery Engine Stability Test

## One-line conclusion
{"L2 discovery is stable enough for production use." if normal_stability["theme_match"]["overlap_pct"] >= 70 else "L2 discovery shows significant variability — prompt engineering needed before trusting results."}

## Data Summary
| Metric | Value |
|--------|-------|
| Symbol | BTCUSDT |
| Timeframe | 1H |
| Data range | 2024-06-01 to 2026-03-17 |
| Bars | {control["patterns_requested"]} patterns requested per run |
| Control (temp=0) | 1 run |
| Normal (temp=0.7) | {len(normal_runs)} runs |
| Total API cost | ~{sum(r['tokens_used'] for r in [control] + normal_runs)} tokens |

## Control Run (temperature=0)
| Pattern | Direction | Entry Conditions | SL/TP ATR |
|---------|-----------|-----------------|-----------|
"""

    for p in control["patterns"]:
        conds = ", ".join(f"{c['field']} {c['op']} {c['value']}" for c in p["entry_conditions"])
        sl = p["exit"]["sl_atr"] or "?"
        tp = p["exit"]["tp_atr"] or "?"
        report += f"| {p['name']} | {p['direction']} | {conds} | {sl}/{tp} |\n"

    report += f"""
## Normal Runs (temperature=0.7) — Stability Metrics

### Exact Pattern Match
- Patterns identical across all 3 runs: **{normal_stability['exact_match']['common_across_all']}**
- Total unique patterns: **{normal_stability['exact_match']['total_unique']}**
- Overlap: **{normal_stability['exact_match']['overlap_pct']}%**

### Theme Match (direction + fields, ignoring exact values)
- Themes common to all 3 runs: **{normal_stability['theme_match']['common_across_all']}**
- Total unique themes: **{normal_stability['theme_match']['total_unique']}**
- Overlap: **{normal_stability['theme_match']['overlap_pct']}%**
- Common themes: {', '.join(normal_stability['theme_match']['common_list']) or 'none'}

### Direction Consistency
"""
    for direction, count in normal_stability["direction_distribution"].items():
        pct = round(count / max(normal_stability["total_patterns"], 1) * 100, 1)
        report += f"- {direction}: {count} ({pct}%)\n"

    report += f"""
### Hour Preference (hour_utc conditions)
"""
    for hour, count in list(normal_stability["hour_distribution"].items())[:5]:
        report += f"- Hour {hour}: appeared {count} times\n"

    report += f"""
### Exit Parameters
- SL ATR range: {normal_stability['exit_stats']['sl_atr_range'][0]} - {normal_stability['exit_stats']['sl_atr_range'][1]} (mean: {normal_stability['exit_stats']['sl_atr_mean']})
- TP ATR range: {normal_stability['exit_stats']['tp_atr_range'][0]} - {normal_stability['exit_stats']['tp_atr_range'][1]} (mean: {normal_stability['exit_stats']['tp_atr_mean']})

## Per-Run Details
"""

    for i, run in enumerate([control] + normal_runs):
        label = "Control (temp=0)" if i == 0 else f"Run {i} (temp=0.7)"
        report += f"\n### {label}\n"
        report += f"- Patterns: {run['patterns_returned']}/{run['patterns_requested']}\n"
        report += f"- Tokens: {run['tokens_used']}\n"
        report += f"- Time: {run['elapsed_seconds']}s\n"
        for p in run["patterns"]:
            conds = ", ".join(f"{c['field']}{c['op']}{c['value']}" for c in p["entry_conditions"])
            report += f"  - **{p['name']}** ({p['direction']}): {conds}\n"

    # Verdict
    theme_pct = normal_stability["theme_match"]["overlap_pct"]
    verdict = "PASS" if theme_pct >= 70 else ("MARGINAL" if theme_pct >= 50 else "FAIL")

    report += f"""
## Verdict: **{verdict}**

- Theme overlap across 3 normal runs: **{theme_pct}%**
- Threshold: >= 70% = PASS, 50-69% = MARGINAL, < 50% = FAIL

## 🔬 Quant Researcher
{"The discovery engine shows sufficient consistency at the theme level. While exact parameters vary (expected with temperature=0.7), the directional bias and time-slot preferences are stable. This means the engine reliably identifies the same *types* of patterns, even if the specific thresholds differ." if verdict == "PASS" else "Significant variability in pattern output. The LLM is finding different patterns each run, which means downstream backtesting results will be noisy. Consider: (1) lowering temperature to 0.3, (2) running multiple discovery rounds and keeping only consensus patterns, (3) adding structural constraints to the prompt."}

## 💼 Business Advisor
{"Good news for the product: users will get consistent insights regardless of when they run the analysis. This is table-stakes for a paid product — if the AI gave different advice every time, no one would trust it." if verdict == "PASS" else "This is a product risk. If a user runs analysis twice and gets different patterns, trust evaporates instantly. Before launching, either fix the consistency or add a 'consensus mode' that explicitly runs multiple times and shows only patterns that appear repeatedly."}

## 🏗️ CTO
{"No code changes needed for stability. The discovery prompt is well-structured enough that the LLM converges on similar themes. For production, consider caching discovery results and only re-running when new data arrives." if verdict == "PASS" else "Engineering fix needed. Options: (1) lower temperature globally (simple, loses exploration), (2) ensemble mode — run 3x and intersect (reliable, 3x cost), (3) add few-shot examples to prompt (moderate effort, good ROI). Recommend option 2 with a `stability_mode=True` flag."}

## Next Steps
- 🔬 Quant: {"Proceed to B2 cross-asset test" if verdict != "FAIL" else "Fix stability first, then re-run B1"}
- 💼 Business: {"Use this stability data in pitch — 'AI gives consistent results'" if verdict == "PASS" else "Add 'consensus mode' to product spec before launch"}
- 🏗️ CTO: {"No action needed" if verdict == "PASS" else "Implement ensemble discovery before proceeding"}
"""

    return report


async def main():
    """Run B1 stability test."""
    logger.info("=" * 60)
    logger.info("B1: L2 Discovery Engine Stability Test")
    logger.info("=" * 60)

    # 1. Fetch data
    series = await fetch_data()

    # 2. Run discovery 4 times
    llm = AnthropicClient()
    try:
        # Control: temperature=0
        control = await run_discovery(llm, series, temperature=0.0, run_id="control")
        control_path = VALIDATION_DIR / "b1_run0_control.json"
        control_path.write_text(json.dumps(control, indent=2))
        logger.info(f"Saved {control_path}")

        # Normal runs: temperature=0.7
        normal_runs = []
        for i in range(1, 4):
            result = await run_discovery(
                llm, series, temperature=0.7, run_id=f"run{i}"
            )
            path = VALIDATION_DIR / f"b1_run{i}_patterns.json"
            path.write_text(json.dumps(result, indent=2))
            logger.info(f"Saved {path}")
            normal_runs.append(result)

            # Small delay to avoid rate limiting
            if i < 3:
                await asyncio.sleep(2)

    finally:
        await llm.close()

    # 3. Compute stability metrics
    stability = compute_stability(normal_runs)

    # 4. Generate report
    report = generate_report(control, normal_runs, stability)
    report_path = VALIDATION_DIR / "b1_stability_report.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info(f"Saved {report_path}")

    # Print summary
    theme_pct = stability["theme_match"]["overlap_pct"]
    verdict = "PASS" if theme_pct >= 70 else ("MARGINAL" if theme_pct >= 50 else "FAIL")
    logger.info(f"\n{'='*60}")
    logger.info(f"B1 RESULT: {verdict} (theme overlap: {theme_pct}%)")
    logger.info(f"{'='*60}")

    return verdict


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result != "FAIL" else 1)

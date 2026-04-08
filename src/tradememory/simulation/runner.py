"""Experiment runner — fetch data and run full A/B + ablation matrix.

Orchestrates:
1. Data fetching (async via Binance)
2. Strategy × symbol × timeframe matrix
3. A/B experiment + ablation for each combination
4. Report generation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List

from tradememory.simulation.experiment import ABExperiment
from tradememory.simulation.presets import PRESET_STRATEGIES
from tradememory.simulation.report import FullExperimentReport

logger = logging.getLogger(__name__)


async def run_full_experiment(
    symbols: List[str] = None,
    timeframes: List[str] = None,
    days: int = 1095,
    is_ratio: float = 0.67,
    output_dir: str = "scripts/research",
) -> Dict[str, Any]:
    """Run full experiment matrix: symbol × timeframe × strategy.

    Args:
        symbols: List of trading pairs (default: ["BTCUSDT", "ETHUSDT"])
        timeframes: List of bar timeframes (default: ["15m", "1h", "4h"])
        days: Days of historical data to fetch (default: 1095 = 3 years)
        is_ratio: In-sample ratio for IS/OOS split (default: 0.67)
        output_dir: Directory for output files

    Returns:
        Dict with results summary and file paths.
    """
    if symbols is None:
        symbols = ["BTCUSDT", "ETHUSDT"]
    if timeframes is None:
        timeframes = ["15m", "1h", "4h"]

    from tradememory.data.binance import BinanceDataSource
    from tradememory.data.models import Timeframe

    datasource = BinanceDataSource()
    all_results: List[Dict[str, Any]] = []

    tf_map = {tf.value: tf for tf in Timeframe}

    for symbol in symbols:
        for tf_str in timeframes:
            tf_enum = tf_map.get(tf_str)
            if tf_enum is None:
                logger.warning("Unknown timeframe %s, skipping", tf_str)
                continue

            # Fetch data
            logger.info("Fetching %s %s (%d days)...", symbol, tf_str, days)
            try:
                series = await datasource.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=tf_enum,
                    days=days,
                )
            except Exception as e:
                logger.error("Failed to fetch %s %s: %s", symbol, tf_str, e)
                continue

            logger.info("Got %d bars for %s %s", len(series.bars), symbol, tf_str)

            for strategy in PRESET_STRATEGIES:
                logger.info(
                    "Running %s on %s %s (%d bars)...",
                    strategy.name, symbol, tf_str, len(series.bars),
                )

                try:
                    experiment = ABExperiment(
                        strategy=strategy,
                        series=series,
                        timeframe_str=tf_str,
                        is_ratio=is_ratio,
                    )

                    # A/B comparison
                    report = experiment.run()

                    # Ablation
                    ablation_results = experiment.ablation()

                    result_entry = {
                        "symbol": symbol,
                        "timeframe": tf_str,
                        "strategy": strategy.name,
                        "bars": len(series.bars),
                        "comparison": {
                            "sharpe_a": report.agent_a.fitness.sharpe_ratio,
                            "sharpe_b": report.agent_b.fitness.sharpe_ratio,
                            "sharpe_improvement": report.sharpe_improvement,
                            "dd_a": report.agent_a.fitness.max_drawdown_pct,
                            "dd_b": report.agent_b.fitness.max_drawdown_pct,
                            "dd_reduction": report.dd_reduction,
                            "trades_a": report.agent_a.fitness.trade_count,
                            "trades_b": report.agent_b.fitness.trade_count,
                            "trades_skipped": report.trades_skipped_by_b,
                            "skipped_pnl": report.pnl_of_skipped_trades,
                            "dqs_pnl_correlation": report.dqs_pnl_correlation,
                            "significance": report.statistical_significance,
                        },
                        "ablation": [
                            {
                                "variant": a.variant_name,
                                "sharpe": a.result.fitness.sharpe_ratio,
                                "sharpe_delta": a.sharpe_delta,
                                "trades": a.result.fitness.trade_count,
                            }
                            for a in ablation_results
                        ],
                    }
                    all_results.append(result_entry)

                    logger.info(
                        "  %s: A=%.4f B=%.4f imp=%+.1f%% skipped=%d",
                        strategy.name,
                        report.agent_a.fitness.sharpe_ratio,
                        report.agent_b.fitness.sharpe_ratio,
                        report.sharpe_improvement * 100,
                        report.trades_skipped_by_b,
                    )

                except Exception as e:
                    logger.error(
                        "Experiment failed for %s/%s/%s: %s",
                        strategy.name, symbol, tf_str, e,
                    )
                    all_results.append({
                        "symbol": symbol,
                        "timeframe": tf_str,
                        "strategy": strategy.name,
                        "error": str(e),
                    })

    # Generate report
    report_obj = FullExperimentReport(results=all_results)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "phase3_results")
    report_obj.save(output_path)

    logger.info("Results saved to %s.json and %s.md", output_path, output_path)

    return {
        "total_experiments": len(all_results),
        "successful": sum(1 for r in all_results if "error" not in r),
        "failed": sum(1 for r in all_results if "error" in r),
        "output_json": output_path + ".json",
        "output_md": output_path + ".md",
        "summary": report_obj.summary_table(),
    }

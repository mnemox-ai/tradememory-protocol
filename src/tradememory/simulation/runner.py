"""Experiment runner — fetch data and run full A/B + ablation matrix.

Orchestrates:
1. Data fetching (async via Binance) with retry logic
2. Strategy x symbol x timeframe matrix
3. A/B experiment + ablation for each combination
4. DSR validation on Agent B OOS results
5. Report generation with partial save
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


async def _fetch_with_retry(datasource, symbol, tf_enum, days, max_retries=3):
    """Fetch OHLCV data with exponential backoff retry."""
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    for attempt in range(max_retries):
        try:
            return await datasource.fetch_ohlcv(
                symbol=symbol,
                timeframe=tf_enum,
                start=start,
                end=end,
            )
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt * 5  # 5, 10, 20 seconds
                logger.warning(
                    "Fetch failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, max_retries, wait, e,
                )
                await asyncio.sleep(wait)
            else:
                raise


def _compute_dsr_for_result(result_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Compute DSR on Agent B's OOS Sharpe if enough trades."""
    try:
        from tradememory.strategy_validator import compute_dsr

        comp = result_entry.get("comparison", {})
        sharpe_b = comp.get("sharpe_b", 0)
        trades_b = comp.get("trades_b", 0)

        if trades_b >= 30:
            return compute_dsr(
                sharpe_raw=sharpe_b,
                num_obs=trades_b,
                num_trials=1,
            )
        else:
            return {
                "sharpe_raw": round(sharpe_b, 6),
                "dsr": 0.0,
                "p_value": 1.0,
                "verdict": "INSUFFICIENT_DATA",
                "num_trials": 1,
                "num_observations": trades_b,
            }
    except Exception as e:
        logger.warning("DSR computation failed: %s", e)
        return {"verdict": "ERROR", "error": str(e)}


async def run_full_experiment(
    symbols: List[str] = None,
    timeframes: List[str] = None,
    days: int = 1095,
    is_ratio: float = 0.67,
    output_dir: str = "scripts/research",
) -> Dict[str, Any]:
    """Run full experiment matrix: symbol x timeframe x strategy.

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

    os.makedirs(output_dir, exist_ok=True)
    partial_path = os.path.join(output_dir, "phase4_partial.json")

    # Progress tracking
    total_runs = len(symbols) * len(timeframes) * len(PRESET_STRATEGIES)
    current = 0

    for symbol in symbols:
        for tf_str in timeframes:
            tf_enum = tf_map.get(tf_str)
            if tf_enum is None:
                logger.warning("Unknown timeframe %s, skipping", tf_str)
                continue

            # Fetch data with retry
            logger.info("Fetching %s %s (%d days)...", symbol, tf_str, days)
            try:
                series = await _fetch_with_retry(datasource, symbol, tf_enum, days)
            except Exception as e:
                logger.error("Failed to fetch %s %s after retries: %s", symbol, tf_str, e)
                for strategy in PRESET_STRATEGIES:
                    current += 1
                    all_results.append({
                        "symbol": symbol,
                        "timeframe": tf_str,
                        "strategy": strategy.name,
                        "error": f"Data fetch failed: {e}",
                    })
                continue

            logger.info("Got %d bars for %s %s", len(series.bars), symbol, tf_str)

            for strategy in PRESET_STRATEGIES:
                current += 1
                logger.info(
                    "[%d/%d] %s x %s x %s (%d bars)...",
                    current, total_runs, symbol, tf_str, strategy.name, len(series.bars),
                )

                try:
                    experiment = ABExperiment(
                        strategy=strategy,
                        series=series,
                        timeframe_str=tf_str,
                        is_ratio=is_ratio,
                    )

                    # A/B comparison (returns enriched report)
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
                            "equity_pnl_a": report.equity_pnl_a,
                            "equity_pnl_b": report.equity_pnl_b,
                            "equity_pnl_improvement": report.equity_pnl_improvement,
                            "equity_dd_a": report.equity_dd_a,
                            "equity_dd_b": report.equity_dd_b,
                            "equity_dd_reduction": report.equity_dd_reduction,
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
                        # Enriched data from experiment
                        "dqs_stats": report.dqs_stats,
                        "tier_pnl": report.tier_pnl,
                        "changepoint_stats": report.changepoint_stats,
                        "skip_precision": report.skip_precision,
                        "skip_precision_count": report.skip_precision_count,
                    }

                    # DSR validation on Agent B OOS
                    result_entry["dsr"] = _compute_dsr_for_result(result_entry)

                    all_results.append(result_entry)

                    logger.info(
                        "  %s: A=%.4f B=%.4f imp=%+.1f%% skipped=%d dsr=%s",
                        strategy.name,
                        report.agent_a.fitness.sharpe_ratio,
                        report.agent_b.fitness.sharpe_ratio,
                        report.sharpe_improvement * 100,
                        report.trades_skipped_by_b,
                        result_entry["dsr"].get("verdict", "N/A"),
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

                # Partial save after each experiment
                try:
                    with open(partial_path, "w") as f:
                        json.dump(all_results, f, indent=2, default=str)
                except Exception:
                    pass

    # Generate final report
    report_obj = FullExperimentReport(results=all_results)

    output_path = os.path.join(output_dir, "phase4_results")
    report_obj.save(output_path)

    logger.info("Results saved to %s.json and %s.md", output_path, output_path)

    # Clean up partial file
    try:
        if os.path.exists(partial_path):
            os.remove(partial_path)
    except Exception:
        pass

    return {
        "total_experiments": len(all_results),
        "successful": sum(1 for r in all_results if "error" not in r),
        "failed": sum(1 for r in all_results if "error" in r),
        "output_json": output_path + ".json",
        "output_md": output_path + ".md",
        "summary": report_obj.summary_table(),
    }

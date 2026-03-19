#!/usr/bin/env python3
"""B2: Cross-Asset Transfer Test — Strategy E on ETHUSDT.

Question: Does Strategy E (built for BTCUSDT) transfer to ETHUSDT?
Method:
  1. Fetch ETHUSDT 1H Jun 2024 - Mar 2026
  2. Backtest Strategy E on full ETHUSDT period
  3. Walk-forward: 6+ non-overlapping 3-month windows
  4. Random baseline: 100 strategies on ETHUSDT, rank Strategy E
  5. Pass: >P70 = transfer works, <P50 = asset-specific

Outputs:
  validation/b2_eth_data_stats.md
  validation/b2_transfer_results.json
  validation/b2_transfer_report.md

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/research/run_b2_transfer.py
"""

import asyncio
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))  # scripts/ for strategy_definitions

from tradememory.data.binance import BinanceDataSource
from tradememory.data.context_builder import ContextConfig, build_context, compute_atr
from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.backtester import (
    _compute_fitness,
    check_entry,
    check_exit_position,
    force_close_position,
    open_position,
)
from tradememory.evolution.models import FitnessMetrics
from tradememory.evolution.random_baseline import (
    RandomStrategyGenerator,
    compute_percentile_rank,
)

from strategy_definitions import build_strategy_e

VALIDATION_DIR = Path(__file__).parent.parent.parent / "validation"
VALIDATION_DIR.mkdir(exist_ok=True)


# --- Reuse optimized helpers from run_real_baseline.py ---

def precompute_contexts(series: OHLCVSeries, config: Optional[ContextConfig] = None):
    """Precompute MarketContext for every bar."""
    cfg = config or ContextConfig()
    n = len(series.bars)
    min_bar = cfg.atr_period + 1
    contexts = [None] * n
    for i in range(min_bar, n):
        if i % 500 == 0:
            print(f"    context {i}/{n}...", flush=True)
        contexts[i] = build_context(series, bar_index=i, config=cfg)
    return contexts


def precompute_atrs(bars: List[OHLCV], atr_period: int = 14):
    """Precompute ATR for every bar."""
    n = len(bars)
    atrs = [None] * n
    for i in range(atr_period + 1, n):
        atrs[i] = compute_atr(bars[max(0, i - atr_period - 1): i + 1], atr_period)
    return atrs


def fast_backtest(
    bars: List[OHLCV],
    contexts: list,
    atrs: list,
    pattern,
    config: Optional[ContextConfig] = None,
    timeframe: str = "1h",
) -> FitnessMetrics:
    """Backtest using precomputed contexts and ATRs."""
    if not bars or len(bars) < 30:
        return FitnessMetrics()
    cfg = config or ContextConfig()
    min_bar = cfg.atr_period + 1
    trades = []
    position = None

    for i in range(min_bar, len(bars)):
        current_bar = bars[i]
        ctx = contexts[i]

        if position is not None:
            trade = check_exit_position(position, current_bar, i)
            if trade is not None:
                trades.append(trade)
                position = None

        if position is None and ctx is not None:
            if check_entry(pattern, ctx):
                atr = atrs[i]
                if atr is None or atr <= 0:
                    continue
                position = open_position(pattern, current_bar, i, atr)

    if position is not None:
        last_bar = bars[-1]
        trade = force_close_position(position, last_bar, len(bars) - 1, "end")
        trades.append(trade)

    return _compute_fitness(trades, timeframe=timeframe)


def fast_backtest_slice(
    bars: List[OHLCV],
    contexts: list,
    atrs: list,
    pattern,
    start_idx: int,
    end_idx: int,
    timeframe: str = "1h",
) -> FitnessMetrics:
    """Backtest a slice of bars using precomputed data."""
    slice_bars = bars[start_idx:end_idx]
    slice_contexts = contexts[start_idx:end_idx]
    slice_atrs = atrs[start_idx:end_idx]
    if not slice_bars or len(slice_bars) < 30:
        return FitnessMetrics()

    cfg = ContextConfig()
    min_bar = cfg.atr_period + 1
    trades = []
    position = None

    for i in range(min_bar, len(slice_bars)):
        current_bar = slice_bars[i]
        ctx = slice_contexts[i]

        if position is not None:
            trade = check_exit_position(position, current_bar, i)
            if trade is not None:
                trades.append(trade)
                position = None

        if position is None and ctx is not None:
            if check_entry(pattern, ctx):
                atr = slice_atrs[i]
                if atr is None or atr <= 0:
                    continue
                position = open_position(pattern, current_bar, i, atr)

    if position is not None:
        last_bar = slice_bars[-1]
        trade = force_close_position(position, last_bar, len(slice_bars) - 1, "end")
        trades.append(trade)

    return _compute_fitness(trades, timeframe=timeframe)


def fast_run_baseline(
    bars: List[OHLCV],
    contexts: list,
    atrs: list,
    n_strategies: int = 100,
    seed: int = 42,
    timeframe: str = "1h",
) -> tuple:
    """Run random baseline, return (sorted sharpes, mean, std)."""
    gen = RandomStrategyGenerator(seed=seed)
    candidates = gen.generate(n_strategies)
    sharpes = []
    for idx, pattern in enumerate(candidates):
        if idx % 25 == 0:
            print(f"    strategy {idx}/{n_strategies}...", flush=True)
        metrics = fast_backtest(bars, contexts, atrs, pattern, timeframe=timeframe)
        sharpes.append(metrics.sharpe_ratio)
    sharpes.sort()
    n = len(sharpes)
    mean_s = sum(sharpes) / n if n > 0 else 0
    var_s = sum((s - mean_s) ** 2 for s in sharpes) / (n - 1) if n > 1 else 0
    std_s = math.sqrt(var_s) if var_s > 0 else 0
    return sharpes, round(mean_s, 4), round(std_s, 4)


def generate_data_stats(bars: List[OHLCV], atrs: list) -> str:
    """Generate ETH data stats markdown."""
    valid_atrs = [a for a in atrs if a is not None]
    avg_atr = sum(valid_atrs) / len(valid_atrs) if valid_atrs else 0
    closes = [b.close for b in bars]
    return f"""# B2: ETHUSDT Data Statistics

| Metric | Value |
|--------|-------|
| Symbol | ETHUSDT |
| Timeframe | 1H |
| Bars | {len(bars)} |
| Date range | {bars[0].timestamp.date()} to {bars[-1].timestamp.date()} |
| Price range | ${min(closes):,.2f} - ${max(closes):,.2f} |
| First close | ${bars[0].close:,.2f} |
| Last close | ${bars[-1].close:,.2f} |
| Avg ATR(14) | ${avg_atr:,.2f} |

*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*
"""


def generate_report(
    data_stats: dict,
    full_metrics: dict,
    window_results: list,
    percentile: float,
    baseline_stats: dict,
) -> str:
    """Generate three-role analysis report."""
    verdict = "PASS" if percentile >= 70 else ("MARGINAL" if percentile >= 50 else "FAIL")
    transfer_label = "transfers" if percentile >= 70 else ("inconclusive" if percentile >= 50 else "asset-specific")

    # Window summary
    positive_windows = sum(1 for w in window_results if w["sharpe"] > 0)
    total_windows = len(window_results)

    report = f"""# B2: Cross-Asset Transfer Test — Strategy E on ETHUSDT

## One-line conclusion
Strategy E {transfer_label} to ETHUSDT (P{percentile:.0f} vs 100 random strategies). {positive_windows}/{total_windows} walk-forward windows positive.

## Test Design
- **Hypothesis**: Strategy E (built on BTCUSDT) has general crypto alpha, not just BTC-specific edge
- **Method**: Backtest identical strategy on ETHUSDT without re-fitting
- **Pass criteria**: >P70 vs random baseline = transfer works, <P50 = asset-specific

## Data Summary
| Metric | Value |
|--------|-------|
| Symbol | ETHUSDT |
| Timeframe | 1H |
| Bars | {data_stats['bars']} |
| Date range | {data_stats['date_range']} |
| Price range | {data_stats['price_range']} |
| Avg ATR(14) | {data_stats['avg_atr']} |

## Full-Period Backtest
| Metric | Value |
|--------|-------|
| Sharpe | {full_metrics['sharpe']:.4f} |
| Trades | {full_metrics['trades']} |
| Win rate | {full_metrics['win_rate']:.1%} |
| Profit factor | {full_metrics['pf']:.2f} |
| Total PnL | {full_metrics['total_pnl']:.2f} |
| Max drawdown | {full_metrics['max_dd']:.1%} |
| Avg holding | {full_metrics['avg_hold']:.1f} bars |
| Expectancy | {full_metrics['expectancy']:.4f} |

## Walk-Forward Results (3-month windows, no re-fitting)
| Window | Period | Sharpe | Trades | Win Rate | PnL |
|--------|--------|--------|--------|----------|-----|
"""

    for i, w in enumerate(window_results):
        report += f"| {i+1} | {w['period']} | {w['sharpe']:.4f} | {w['trades']} | {w['win_rate']:.1%} | {w['total_pnl']:.2f} |\n"

    avg_sharpe = sum(w["sharpe"] for w in window_results) / total_windows if total_windows else 0
    report += f"| **Avg** | | **{avg_sharpe:.4f}** | | | |\n"

    report += f"""
### Walk-Forward Summary
- Positive windows: {positive_windows}/{total_windows}
- Average Sharpe: {avg_sharpe:.4f}
- Best window: {max(w['sharpe'] for w in window_results):.4f}
- Worst window: {min(w['sharpe'] for w in window_results):.4f}

## Random Baseline Ranking
| Metric | Value |
|--------|-------|
| Random strategies | {baseline_stats['n_random']} |
| Random mean Sharpe | {baseline_stats['mean_sharpe']:.4f} |
| Random std Sharpe | {baseline_stats['std_sharpe']:.4f} |
| Strategy E Sharpe | {full_metrics['sharpe']:.4f} |
| **Percentile rank** | **P{percentile:.1f}** |

## Verdict: **{verdict}** — Strategy E {transfer_label} to ETHUSDT

## Quant Researcher
"""

    if verdict == "PASS":
        report += "Strategy E shows genuine cross-asset alpha. The US afternoon momentum pattern (long at 14:00 UTC with positive 12h trend) captures a market microstructure effect that exists in both BTC and ETH. This makes sense — both assets share the same institutional trading hours and similar intraday liquidity patterns. The strategy is capturing *crypto market structure*, not BTC-specific dynamics.\n"
    elif verdict == "MARGINAL":
        report += f"Inconclusive. P{percentile:.0f} means Strategy E performs somewhat better than random on ETH, but not convincingly. The pattern may partially transfer — crypto assets share some microstructure — but ETH has its own dynamics (DeFi activity, staking flows) that differ from BTC. Consider: the strategy might work in correlated regimes but fail when ETH decouples from BTC.\n"
    else:
        report += f"Strategy E does NOT transfer to ETHUSDT (P{percentile:.0f}). The US afternoon momentum pattern is BTC-specific, likely driven by BTC-dominant institutional flows (ETF inflows, CME basis trades) that don't directly affect ETH. This is actually useful information — it tells us the Evolution Engine found a *real* BTC-specific signal, not just generic trend-following.\n"

    report += "\n## Business Advisor\n"
    if verdict == "PASS":
        report += "Strong product signal: the Evolution Engine finds patterns that generalize across crypto assets. This means you can market multi-asset support with confidence. One evolution run on BTC could seed strategies for the entire crypto portfolio.\n"
    elif verdict == "MARGINAL":
        report += "Be careful with claims. Don't promise multi-asset transfer until the signal is stronger. Position it as 'BTC-optimized with ETH potential' rather than 'universal crypto alpha'. Users who test on ETH might see weaker results and lose trust.\n"
    else:
        report += "The strategy is BTC-specific. This is fine — position the Evolution Engine as discovering *asset-specific* patterns. Each asset needs its own evolution run. This is actually a selling point: 'Our AI finds patterns unique to each asset, not generic indicators.'\n"

    report += "\n## CTO\n"
    if verdict == "PASS":
        report += "Engineering implication: add a `transfer_test` step to the evolution pipeline. After discovering patterns on one asset, automatically backtest on correlated assets to flag which patterns generalize. This is a cheap validation step that adds significant value.\n"
    elif verdict == "MARGINAL":
        report += "Don't build cross-asset features yet. The transfer is weak enough that automatic cross-asset deployment would disappoint users. Keep it as an experimental analysis tool, not an automated pipeline step.\n"
    else:
        report += "Build per-asset evolution as the default. Each asset gets its own discovery run. Don't try to share strategies across assets — it doesn't work for Strategy E, and likely won't work for other patterns. The architecture should make per-asset runs cheap and fast.\n"

    report += f"""
## Comparison: BTC vs ETH Performance
- Strategy E on BTC (Phase 13): Sharpe ~4.42, P100 (reference)
- Strategy E on ETH (this test): Sharpe {full_metrics['sharpe']:.4f}, P{percentile:.0f}
- Transfer ratio: {full_metrics['sharpe'] / 4.42:.1%} of BTC performance (if BTC Sharpe ~4.42)

## Next Steps
- Quant: {"Test on SOL/DOGE for broader validation" if verdict == "PASS" else "Run Evolution Engine directly on ETHUSDT for ETH-specific patterns"}
- Business: {"Add 'multi-asset validated' to marketing" if verdict == "PASS" else "Position as asset-specific pattern discovery"}
- CTO: {"Add automatic transfer test to pipeline" if verdict == "PASS" else "Build per-asset evolution pipeline"}

*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*
"""
    return report


async def main():
    print("=" * 70)
    print("B2: Cross-Asset Transfer Test — Strategy E on ETHUSDT")
    print("=" * 70)

    # --- Step 1: Fetch ETHUSDT data ---
    print("\n[1/5] Fetching ETHUSDT 1H data from Binance...")
    start_dt = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end_dt = datetime(2026, 3, 19, tzinfo=timezone.utc)

    binance = BinanceDataSource()
    try:
        series = await binance.fetch_ohlcv(
            symbol="ETHUSDT",
            timeframe=Timeframe.H1,
            start=start_dt,
            end=end_dt,
        )
    finally:
        await binance.close()

    bars = series.bars
    print(f"  Bars: {series.count}")
    print(f"  Period: {series.start} -> {series.end}")
    print(f"  First close: ${bars[0].close:,.2f}")
    print(f"  Last close: ${bars[-1].close:,.2f}")

    # --- Step 2: Precompute contexts + ATR ---
    print("\n[2/5] Precomputing MarketContext + ATR for all bars...")
    t0 = time.time()
    contexts = precompute_contexts(series)
    atrs = precompute_atrs(bars)
    precompute_time = time.time() - t0
    valid_ctx = sum(1 for c in contexts if c is not None)
    print(f"  Done in {precompute_time:.1f}s ({valid_ctx} valid contexts)")

    # Save data stats
    valid_atrs = [a for a in atrs if a is not None]
    avg_atr = sum(valid_atrs) / len(valid_atrs) if valid_atrs else 0
    closes = [b.close for b in bars]
    data_stats_md = generate_data_stats(bars, atrs)
    (VALIDATION_DIR / "b2_eth_data_stats.md").write_text(data_stats_md, encoding="utf-8")
    print(f"  Saved validation/b2_eth_data_stats.md")

    data_stats = {
        "bars": len(bars),
        "date_range": f"{bars[0].timestamp.date()} to {bars[-1].timestamp.date()}",
        "price_range": f"${min(closes):,.2f} - ${max(closes):,.2f}",
        "avg_atr": f"${avg_atr:,.2f}",
    }

    # --- Step 3: Full-period backtest ---
    print("\n[3/5] Backtesting Strategy E on full ETHUSDT...")
    pattern = build_strategy_e()
    full_metrics = fast_backtest(bars, contexts, atrs, pattern, timeframe="1h")
    full_results = {
        "sharpe": full_metrics.sharpe_ratio,
        "expectancy": full_metrics.expectancy,
        "trades": full_metrics.trade_count,
        "win_rate": full_metrics.win_rate,
        "pf": full_metrics.profit_factor,
        "total_pnl": full_metrics.total_pnl,
        "max_dd": full_metrics.max_drawdown_pct,
        "avg_hold": full_metrics.avg_holding_bars,
    }
    print(f"  Sharpe={full_metrics.sharpe_ratio:.4f}, trades={full_metrics.trade_count}, "
          f"WR={full_metrics.win_rate:.1%}, PF={full_metrics.profit_factor:.2f}, "
          f"expectancy={full_metrics.expectancy:.4f}")

    # --- Step 4: Walk-forward (3-month windows) ---
    print("\n[4/5] Walk-forward: 3-month windows...")
    # Split into ~3-month windows (approx 90 days * 24 bars = 2160 bars)
    window_size = 2160  # ~3 months of 1H bars
    n_bars = len(bars)
    windows = []
    start_idx = 0
    while start_idx + window_size <= n_bars:
        windows.append((start_idx, start_idx + window_size))
        start_idx += window_size
    # Add remaining bars as final window if >= 30 bars
    if n_bars - start_idx >= 30:
        windows.append((start_idx, n_bars))

    print(f"  {len(windows)} windows of ~{window_size} bars each")

    window_results = []
    for i, (w_start, w_end) in enumerate(windows):
        w_metrics = fast_backtest_slice(bars, contexts, atrs, pattern, w_start, w_end)
        period = f"{bars[w_start].timestamp.date()} to {bars[min(w_end-1, n_bars-1)].timestamp.date()}"
        result = {
            "window": i + 1,
            "period": period,
            "start_idx": w_start,
            "end_idx": w_end,
            "bars": w_end - w_start,
            "sharpe": w_metrics.sharpe_ratio,
            "trades": w_metrics.trade_count,
            "win_rate": w_metrics.win_rate,
            "pf": w_metrics.profit_factor,
            "total_pnl": w_metrics.total_pnl,
            "max_dd": w_metrics.max_drawdown_pct,
        }
        window_results.append(result)
        print(f"  Window {i+1}: {period} | Sharpe={w_metrics.sharpe_ratio:.4f}, "
              f"trades={w_metrics.trade_count}, WR={w_metrics.win_rate:.1%}")

    # --- Step 5: Random baseline ranking ---
    print("\n[5/5] Running 100 random strategies on ETHUSDT...")
    t1 = time.time()
    sharpes, mean_sharpe, std_sharpe = fast_run_baseline(
        bars, contexts, atrs, n_strategies=100, seed=42, timeframe="1h"
    )
    baseline_time = time.time() - t1
    print(f"  Done in {baseline_time:.1f}s")
    print(f"  Random mean Sharpe: {mean_sharpe:.4f}, std: {std_sharpe:.4f}")

    percentile = compute_percentile_rank(full_metrics.sharpe_ratio, sharpes)
    print(f"  Strategy E Sharpe: {full_metrics.sharpe_ratio:.4f} → P{percentile:.1f}")

    baseline_stats = {
        "n_random": 100,
        "mean_sharpe": mean_sharpe,
        "std_sharpe": std_sharpe,
        "seed": 42,
    }

    # --- Save results ---
    verdict = "PASS" if percentile >= 70 else ("MARGINAL" if percentile >= 50 else "FAIL")

    print(f"\n{'='*70}")
    print(f"VERDICT: {verdict} — Strategy E {'transfers' if percentile >= 70 else 'does NOT transfer'} to ETHUSDT (P{percentile:.0f})")
    print(f"{'='*70}")

    # JSON results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test": "B2_cross_asset_transfer",
        "source_asset": "BTCUSDT",
        "target_asset": "ETHUSDT",
        "data_period": f"{bars[0].timestamp.date()} to {bars[-1].timestamp.date()}",
        "bars": len(bars),
        "full_period": full_results,
        "walk_forward": {
            "window_size_bars": window_size,
            "n_windows": len(window_results),
            "windows": window_results,
            "positive_windows": sum(1 for w in window_results if w["sharpe"] > 0),
            "avg_sharpe": round(sum(w["sharpe"] for w in window_results) / len(window_results), 4) if window_results else 0,
        },
        "baseline": {
            "n_random": 100,
            "seed": 42,
            "mean_sharpe": mean_sharpe,
            "std_sharpe": std_sharpe,
            "percentile_rank": round(percentile, 1),
        },
        "verdict": verdict,
    }
    json_path = VALIDATION_DIR / "b2_transfer_results.json"
    json_path.write_text(json.dumps(output, indent=2))
    print(f"\nSaved {json_path}")

    # Report
    report = generate_report(data_stats, full_results, window_results, percentile, baseline_stats)
    report_path = VALIDATION_DIR / "b2_transfer_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Saved {report_path}")


if __name__ == "__main__":
    asyncio.run(main())

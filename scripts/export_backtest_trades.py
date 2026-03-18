#!/usr/bin/env python3
"""Export Strategy E backtest trades to JSON.

Fetches BTCUSDT 1H data from Binance (2024-06-01 to 2026-03-18),
runs Strategy E backtest, and exports each trade with full metadata.

Usage:
    cd C:/Users/johns/projects/tradememory-protocol
    python scripts/export_backtest_trades.py
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tradememory.data.binance import BinanceDataSource
from tradememory.data.context_builder import ContextConfig, build_context, compute_atr
from tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from tradememory.evolution.backtester import (
    Position,
    Trade,
    _check_exit,
    _compute_fitness,
    _force_close,
    _open_position,
    check_entry,
)
from tradememory.evolution.models import (
    CandidatePattern,
    FitnessMetrics,
)


def precompute_contexts(series: OHLCVSeries, config: Optional[ContextConfig] = None):
    """Precompute MarketContext for every bar in the series."""
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
    """Precompute ATR for every bar in the series."""
    n = len(bars)
    atrs = [None] * n
    for i in range(atr_period + 1, n):
        atrs[i] = compute_atr(bars[max(0, i - atr_period - 1) : i + 1], atr_period)
    return atrs


def fast_backtest_with_trades(
    bars: List[OHLCV],
    contexts: list,
    atrs: list,
    pattern: CandidatePattern,
    config: Optional[ContextConfig] = None,
    timeframe: str = "1h",
) -> Tuple[FitnessMetrics, List[Trade]]:
    """Backtest returning both FitnessMetrics and the list of Trade objects."""
    if not bars or len(bars) < 30:
        return FitnessMetrics(), []
    cfg = config or ContextConfig()
    min_bar = cfg.atr_period + 1
    trades: List[Trade] = []
    position: Optional[Position] = None

    for i in range(min_bar, len(bars)):
        current_bar = bars[i]
        ctx = contexts[i]

        if position is not None:
            trade = _check_exit(position, current_bar, i)
            if trade is not None:
                trades.append(trade)
                position = None

        if position is None and ctx is not None:
            if check_entry(pattern, ctx):
                atr = atrs[i]
                if atr is None or atr <= 0:
                    continue
                position = _open_position(pattern, current_bar, i, atr)

    if position is not None:
        last_bar = bars[-1]
        trade = _force_close(position, last_bar, len(bars) - 1, "end")
        trades.append(trade)

    fitness = _compute_fitness(trades, timeframe=timeframe)
    return fitness, trades


from strategy_definitions import build_strategy_e  # noqa: E402


def trade_to_dict(
    trade: Trade,
    bars: List[OHLCV],
    contexts: list,
    atrs: list,
    strategy_id: str = "STRAT-E",
    symbol: str = "BTCUSDT",
) -> dict:
    """Convert a Trade dataclass to a rich dict with metadata."""
    entry_bar = bars[trade.entry_bar]
    exit_bar = bars[trade.exit_bar]

    # ATR at entry
    atr_at_entry = atrs[trade.entry_bar]

    # trend_12h_pct at entry
    ctx = contexts[trade.entry_bar]
    trend_12h_pct = ctx.trend_12h_pct if ctx and ctx.trend_12h_pct is not None else None

    # pnl_r = pnl / risk (risk = 1 ATR for SL)
    pnl_r = None
    if atr_at_entry and atr_at_entry > 0:
        pnl_r = round(trade.pnl / atr_at_entry, 4)

    # pnl_pct = pnl / entry_price * 100
    pnl_pct = round(trade.pnl / trade.entry_price * 100, 4) if trade.entry_price else 0.0

    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "direction": trade.direction,
        "entry_price": round(trade.entry_price, 2),
        "exit_price": round(trade.exit_price, 2),
        "entry_time": entry_bar.timestamp.isoformat(),
        "exit_time": exit_bar.timestamp.isoformat(),
        "pnl_pct": pnl_pct,
        "pnl_r": pnl_r,
        "exit_reason": trade.exit_reason,
        "holding_bars": trade.holding_bars,
        "atr_at_entry": round(atr_at_entry, 2) if atr_at_entry else None,
        "trend_12h_pct": round(trend_12h_pct, 4) if trend_12h_pct is not None else None,
        "trade_type": "backtest",
    }


async def main():
    print("=== Export Strategy E Backtest Trades ===\n")

    # 1. Fetch data
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2026, 3, 18, tzinfo=timezone.utc)
    symbol = "BTCUSDT"
    timeframe = Timeframe.H1

    print(f"Fetching {symbol} {timeframe.value} from {start.date()} to {end.date()}...")
    ds = BinanceDataSource()
    try:
        series = await ds.fetch_ohlcv(symbol, timeframe, start, end)
    finally:
        await ds.close()
    print(f"  Got {len(series.bars)} bars\n")

    # 2. Precompute
    print("Precomputing contexts...")
    contexts = precompute_contexts(series)
    print("Precomputing ATRs...")
    atrs = precompute_atrs(series.bars)

    # 3. Run backtest
    strategy = build_strategy_e()
    print(f"\nRunning backtest: {strategy.name}...")
    fitness, trades = fast_backtest_with_trades(
        series.bars, contexts, atrs, strategy, timeframe="1h"
    )

    # 4. Convert trades to dicts
    trade_dicts = [
        trade_to_dict(t, series.bars, contexts, atrs, strategy_id="STRAT-E", symbol=symbol)
        for t in trades
    ]

    # 5. Write JSON
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "strategy_e_backtest.json"
    output_path.write_text(json.dumps(trade_dicts, indent=2), encoding="utf-8")
    print(f"\nWrote {len(trade_dicts)} trades to {output_path}")

    # 6. Summary
    print(f"\n--- Summary ---")
    print(f"  Trades:        {fitness.trade_count}")
    print(f"  Win Rate:      {fitness.win_rate:.1%}")
    print(f"  Sharpe:        {fitness.sharpe_ratio:.2f}")
    print(f"  Profit Factor: {fitness.profit_factor:.2f}")
    print(f"  Total PnL:     {fitness.total_pnl:.2f}")
    print(f"  Max Drawdown:  {fitness.max_drawdown_pct:.1f}%")
    print(f"  Avg Holding:   {fitness.avg_holding_bars:.1f} bars")

    if trade_dicts:
        wins = [t for t in trade_dicts if t["pnl_pct"] > 0]
        losses = [t for t in trade_dicts if t["pnl_pct"] <= 0]
        print(f"  Wins:          {len(wins)}")
        print(f"  Losses:        {len(losses)}")
        first = trade_dicts[0]["entry_time"][:10]
        last = trade_dicts[-1]["exit_time"][:10]
        print(f"  Period:        {first} → {last}")


if __name__ == "__main__":
    asyncio.run(main())

"""Vectorized backtester for evolution hypotheses.

Pure Python, no external backtest libraries.
Input: OHLCVSeries + CandidatePattern → FitnessMetrics

Design:
- Iterates bar-by-bar (simulates live execution)
- Evaluates entry conditions against MarketContext at each bar
- Manages single position (no pyramiding)
- SL/TP/time-based exits via ATR multiples
- Computes FitnessMetrics from trade log
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from tradememory.data.context_builder import (
    ContextConfig,
    MarketContext,
    build_context,
    compute_atr,
)
from tradememory.data.models import OHLCV, OHLCVSeries
from tradememory.evolution.models import (
    CandidatePattern,
    ConditionOperator,
    ExitCondition,
    FitnessMetrics,
    RuleCondition,
)

logger = logging.getLogger(__name__)


# --- Annualization factor ---

_ANNUALIZATION_MAP = {
    "1m": math.sqrt(252 * 24 * 60),
    "5m": math.sqrt(252 * 24 * 12),
    "15m": math.sqrt(252 * 24 * 4),
    "30m": math.sqrt(252 * 24 * 2),
    "1h": math.sqrt(252 * 24),
    "4h": math.sqrt(252 * 6),
    "1d": math.sqrt(252),
    "1w": math.sqrt(52),
}


def get_annualization_factor(timeframe_str: str) -> float:
    """Return sqrt(N) annualization factor for Sharpe ratio.

    Args:
        timeframe_str: One of "1m","5m","15m","30m","1h","4h","1d","1w".

    Returns:
        sqrt(bars_per_year) for the given timeframe.

    Raises:
        ValueError: If timeframe_str is not recognized.
    """
    factor = _ANNUALIZATION_MAP.get(timeframe_str)
    if factor is None:
        raise ValueError(f"Unknown timeframe: {timeframe_str!r}. Expected one of {list(_ANNUALIZATION_MAP)}")
    return factor


# --- Trade log ---


@dataclass
class Trade:
    """Single completed trade."""

    entry_bar: int
    exit_bar: int
    direction: str  # "long" or "short"
    entry_price: float
    exit_price: float
    pnl: float = 0.0
    exit_reason: str = ""  # "sl", "tp", "time", "end"
    holding_bars: int = 0


@dataclass
class Position:
    """Open position during backtest."""

    entry_bar: int
    direction: str
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    max_holding_bars: Optional[int] = None


# --- Condition evaluation ---


def evaluate_condition(condition: RuleCondition, context: MarketContext) -> bool:
    """Evaluate a single rule condition against market context.

    Returns True if condition is met.
    """
    value = _get_context_field(context, condition.field)
    if value is None:
        return False

    target = condition.value
    op = condition.op

    if op == ConditionOperator.GT:
        return value > target
    elif op == ConditionOperator.GTE:
        return value >= target
    elif op == ConditionOperator.LT:
        return value < target
    elif op == ConditionOperator.LTE:
        return value <= target
    elif op == ConditionOperator.EQ:
        return value == target
    elif op == ConditionOperator.NEQ:
        return value != target
    elif op == ConditionOperator.BETWEEN:
        if isinstance(target, (list, tuple)) and len(target) == 2:
            return target[0] <= value <= target[1]
        return False
    elif op == ConditionOperator.IN:
        if isinstance(target, (list, tuple)):
            return value in target
        return False

    return False


def _get_context_field(ctx: MarketContext, field_name: str):
    """Get a field value from MarketContext, handling enum → string."""
    val = getattr(ctx, field_name, None)
    if val is None:
        return None
    # Convert enums to their string value for comparison
    if hasattr(val, "value"):
        return val.value
    return val


def check_entry(pattern: CandidatePattern, context: MarketContext) -> bool:
    """Check if all entry conditions are met (AND logic).

    Returns True if pattern should trigger entry.
    """
    conditions = pattern.entry_condition.conditions
    if not conditions:
        return False  # no conditions = never enter (safety)

    # Check validity conditions first
    validity = pattern.validity_conditions
    if validity.regime and context.regime:
        if context.regime.value != validity.regime:
            return False
    if validity.volatility_regime and context.volatility_regime:
        if context.volatility_regime.value != validity.volatility_regime:
            return False
    if validity.session and context.session:
        if context.session.value != validity.session:
            return False

    # Check all entry conditions (AND)
    return all(evaluate_condition(c, context) for c in conditions)


# --- Backtest engine ---


def backtest(
    series: OHLCVSeries,
    pattern: CandidatePattern,
    context_config: Optional[ContextConfig] = None,
    timeframe: str = "1h",
) -> FitnessMetrics:
    """Run vectorized backtest of a pattern on OHLCV data.

    Args:
        series: OHLCV data (typically H1).
        pattern: CandidatePattern with entry/exit rules.
        context_config: Optional config for context computation.
        timeframe: Bar timeframe for Sharpe annualization (e.g. "1h", "1d").

    Returns:
        FitnessMetrics with backtest results.
    """
    if not series.bars or len(series.bars) < 30:
        return FitnessMetrics()

    config = context_config or ContextConfig()
    bars = series.bars
    trades: List[Trade] = []
    position: Optional[Position] = None

    # Pre-compute ATR for the whole series (used for SL/TP sizing)
    # We need at least atr_period + 1 bars before we can compute
    min_bar = config.atr_period + 1

    for i in range(min_bar, len(bars)):
        current_bar = bars[i]

        # Compute context for this bar
        ctx = build_context(series, bar_index=i, config=config)

        if position is not None:
            # Check exits
            trade = _check_exit(position, current_bar, i)
            if trade is not None:
                trades.append(trade)
                position = None

        if position is None:
            # Check entry
            if check_entry(pattern, ctx):
                # Compute ATR for position sizing
                atr = compute_atr(bars[max(0, i - config.atr_period - 1): i + 1], config.atr_period)
                if atr is None or atr <= 0:
                    continue

                position = _open_position(
                    pattern, current_bar, i, atr
                )

    # Close any remaining position at last bar
    if position is not None:
        last_bar = bars[-1]
        trade = _force_close(position, last_bar, len(bars) - 1, "end")
        trades.append(trade)

    return _compute_fitness(trades, timeframe=timeframe)


def _open_position(
    pattern: CandidatePattern,
    bar: OHLCV,
    bar_idx: int,
    atr: float,
) -> Position:
    """Open a new position."""
    entry_price = bar.close
    direction = pattern.entry_condition.direction
    exit_rules = pattern.exit_condition

    # Compute SL/TP from ATR multiples
    sl = None
    tp = None

    if exit_rules.stop_loss_atr:
        sl_dist = atr * exit_rules.stop_loss_atr
        if direction == "long":
            sl = entry_price - sl_dist
        else:
            sl = entry_price + sl_dist

    if exit_rules.take_profit_atr:
        tp_dist = atr * exit_rules.take_profit_atr
        if direction == "long":
            tp = entry_price + tp_dist
        else:
            tp = entry_price - tp_dist

    return Position(
        entry_bar=bar_idx,
        direction=direction,
        entry_price=entry_price,
        stop_loss=sl,
        take_profit=tp,
        max_holding_bars=exit_rules.max_holding_bars,
    )


def _check_exit(
    position: Position,
    bar: OHLCV,
    bar_idx: int,
) -> Optional[Trade]:
    """Check if position should exit on this bar.

    Checks SL/TP against bar high/low (intra-bar execution).
    """
    holding = bar_idx - position.entry_bar

    # Time-based exit
    if position.max_holding_bars and holding >= position.max_holding_bars:
        return _force_close(position, bar, bar_idx, "time")

    if position.direction == "long":
        # SL hit: bar low touches SL
        if position.stop_loss and bar.low <= position.stop_loss:
            return _close_at(position, position.stop_loss, bar_idx, "sl")
        # TP hit: bar high touches TP
        if position.take_profit and bar.high >= position.take_profit:
            return _close_at(position, position.take_profit, bar_idx, "tp")
    else:  # short
        # SL hit: bar high touches SL
        if position.stop_loss and bar.high >= position.stop_loss:
            return _close_at(position, position.stop_loss, bar_idx, "sl")
        # TP hit: bar low touches TP
        if position.take_profit and bar.low <= position.take_profit:
            return _close_at(position, position.take_profit, bar_idx, "tp")

    return None


def _close_at(
    position: Position,
    exit_price: float,
    bar_idx: int,
    reason: str,
) -> Trade:
    """Close position at a specific price."""
    if position.direction == "long":
        pnl = exit_price - position.entry_price
    else:
        pnl = position.entry_price - exit_price

    return Trade(
        entry_bar=position.entry_bar,
        exit_bar=bar_idx,
        direction=position.direction,
        entry_price=position.entry_price,
        exit_price=exit_price,
        pnl=pnl,
        exit_reason=reason,
        holding_bars=bar_idx - position.entry_bar,
    )


def _force_close(
    position: Position,
    bar: OHLCV,
    bar_idx: int,
    reason: str,
) -> Trade:
    """Force close at bar's close price."""
    return _close_at(position, bar.close, bar_idx, reason)


# --- Fitness computation ---


def _compute_fitness(trades: List[Trade], timeframe: str = "1h") -> FitnessMetrics:
    """Compute FitnessMetrics from trade log."""
    if not trades:
        return FitnessMetrics()

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_pnl = sum(pnls)
    trade_count = len(trades)
    win_count = len(wins)
    win_rate = win_count / trade_count if trade_count > 0 else 0

    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0
    )

    avg_trade_pnl = total_pnl / trade_count if trade_count > 0 else 0
    avg_holding = sum(t.holding_bars for t in trades) / trade_count if trade_count > 0 else 0

    # Sharpe ratio (annualized using timeframe-appropriate factor)
    if len(pnls) > 1:
        mean_pnl = total_pnl / len(pnls)
        var_pnl = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
        std_pnl = math.sqrt(var_pnl) if var_pnl > 0 else 0
        ann_factor = get_annualization_factor(timeframe)
        sharpe = (mean_pnl / std_pnl) * ann_factor if std_pnl > 0 else 0
    else:
        sharpe = 0

    # Max drawdown
    max_dd = _compute_max_drawdown(pnls)

    # Expectancy
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    expectancy = avg_win * win_rate - avg_loss * (1 - win_rate)

    # Max consecutive losses
    max_consec = _max_consecutive_losses(pnls)

    return FitnessMetrics(
        sharpe_ratio=round(sharpe, 4),
        win_rate=round(win_rate, 4),
        profit_factor=round(min(profit_factor, 999.0), 4),  # cap inf
        total_pnl=round(total_pnl, 4),
        max_drawdown_pct=round(max_dd, 4),
        trade_count=trade_count,
        avg_trade_pnl=round(avg_trade_pnl, 4),
        avg_holding_bars=round(avg_holding, 2),
        expectancy=round(expectancy, 4),
        consecutive_losses_max=max_consec,
    )


def _compute_max_drawdown(pnls: List[float]) -> float:
    """Compute max drawdown as percentage of peak equity."""
    if not pnls:
        return 0

    equity = 0
    peak = 0
    max_dd = 0

    for pnl in pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (peak - equity) / peak * 100
            max_dd = max(max_dd, dd)

    return max_dd


def _max_consecutive_losses(pnls: List[float]) -> int:
    """Count maximum consecutive losing trades."""
    max_streak = 0
    current = 0
    for p in pnls:
        if p <= 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak

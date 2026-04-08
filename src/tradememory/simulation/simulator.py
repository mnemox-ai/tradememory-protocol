"""Bar-by-bar simulator that runs an agent through OHLCV data.

Reuses position management logic from evolution/backtester.py:
- ATR-based SL/TP
- Trailing stops
- Time-based exits
- Single position (no pyramiding)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from tradememory.data.context_builder import ContextConfig, build_context, compute_atr
from tradememory.data.models import OHLCVSeries
from tradememory.evolution.backtester import (
    Position,
    Trade,
    _compute_fitness,
    check_exit_position,
    force_close_position,
    open_position,
)
from tradememory.evolution.models import FitnessMetrics
from tradememory.simulation.agent import BaseAgent, SimulatedTrade, TradeSignal


@dataclass
class SimulationResult:
    """Full results from running one agent on one data series."""

    agent_name: str
    strategy_name: str
    symbol: str
    timeframe: str
    fitness: FitnessMetrics
    trades: List[SimulatedTrade] = field(default_factory=list)
    dqs_log: List[dict] = field(default_factory=list)
    changepoint_log: List[dict] = field(default_factory=list)
    skipped_signals: int = 0
    total_signals: int = 0


class Simulator:
    """Bar-by-bar simulation engine.

    Walks through each bar, asks the agent for trade signals,
    manages open positions using backtester's SL/TP/trailing logic,
    and feeds completed trades back to the agent.
    """

    def __init__(
        self,
        agent: BaseAgent,
        series: OHLCVSeries,
        timeframe_str: str = "1h",
        context_config: Optional[ContextConfig] = None,
    ):
        self.agent = agent
        self.series = series
        self.timeframe_str = timeframe_str
        self.config = context_config or ContextConfig()

    def run(self) -> SimulationResult:
        """Run the full simulation bar-by-bar.

        Returns SimulationResult with fitness metrics and trade log.
        """
        bars = self.series.bars
        if not bars or len(bars) < 30:
            return SimulationResult(
                agent_name=self.agent.name,
                strategy_name=self.agent.strategy.name,
                symbol=self.series.symbol,
                timeframe=self.timeframe_str,
                fitness=FitnessMetrics(),
            )

        # Set current symbol on agent for memory storage
        if hasattr(self.agent, '_current_symbol'):
            self.agent._current_symbol = self.series.symbol
        else:
            self.agent._current_symbol = self.series.symbol

        position: Optional[Position] = None
        pending_signal: Optional[TradeSignal] = None
        backtester_trades: List[Trade] = []
        sim_trades: List[SimulatedTrade] = []
        total_signals = 0

        min_bar = self.config.atr_period + 1

        for i in range(min_bar, len(bars)):
            current_bar = bars[i]

            # Check exits on open position
            if position is not None:
                bt_trade = check_exit_position(position, current_bar, i)
                if bt_trade is not None:
                    backtester_trades.append(bt_trade)
                    sim_trade = self._bt_trade_to_sim(bt_trade, pending_signal)
                    sim_trades.append(sim_trade)
                    self.agent.on_trade_complete(sim_trade)
                    position = None
                    pending_signal = None

            # Check entry when flat
            if position is None:
                ctx = build_context(self.series, bar_index=i, config=self.config)
                signal = self.agent.should_trade(ctx)

                if signal is not None:
                    total_signals += 1
                    # Compute ATR for position sizing
                    atr = compute_atr(
                        bars[max(0, i - self.config.atr_period - 1): i + 1],
                        self.config.atr_period,
                    )
                    if atr is not None and atr > 0:
                        position = open_position(
                            self.agent.strategy, current_bar, i, atr
                        )
                        pending_signal = signal
                elif check_entry_would_trigger(self.agent, ctx):
                    # Agent's base conditions met but calibration rejected it
                    total_signals += 1

        # Close any remaining position at last bar
        if position is not None:
            bt_trade = force_close_position(position, bars[-1], len(bars) - 1, "end")
            backtester_trades.append(bt_trade)
            sim_trade = self._bt_trade_to_sim(bt_trade, pending_signal)
            sim_trades.append(sim_trade)
            self.agent.on_trade_complete(sim_trade)

        # Compute fitness from backtester trades
        fitness = _compute_fitness(backtester_trades, timeframe=self.timeframe_str)

        # Collect agent-specific logs
        dqs_log = getattr(self.agent, 'dqs_log', [])
        cp_log = getattr(self.agent, 'changepoint_log', [])
        skipped = getattr(self.agent, 'skipped_signals', 0)

        return SimulationResult(
            agent_name=self.agent.name,
            strategy_name=self.agent.strategy.name,
            symbol=self.series.symbol,
            timeframe=self.timeframe_str,
            fitness=fitness,
            trades=sim_trades,
            dqs_log=dqs_log,
            changepoint_log=cp_log,
            skipped_signals=skipped,
            total_signals=total_signals + skipped,
        )

    def _bt_trade_to_sim(
        self, bt_trade: Trade, signal: Optional[TradeSignal]
    ) -> SimulatedTrade:
        """Convert backtester Trade to SimulatedTrade."""
        lot = signal.lot_size if signal else self.agent.fixed_lot

        # Compute pnl_r: pnl / (entry_price * SL_distance) as R-multiple
        # Approximate: use SL ATR distance from strategy
        sl_atr = self.agent.strategy.exit_condition.stop_loss_atr
        if sl_atr and sl_atr > 0 and bt_trade.entry_price > 0:
            # Risk per unit ≈ entry_price * some fraction
            # Use absolute PnL / approximate risk
            pnl_r = bt_trade.pnl / (bt_trade.entry_price * sl_atr * 0.01) if bt_trade.entry_price > 0 else 0.0
        else:
            pnl_r = bt_trade.pnl / max(bt_trade.entry_price * 0.01, 0.001)

        return SimulatedTrade(
            trade_id=f"sim-{uuid.uuid4().hex[:8]}",
            entry_bar_index=bt_trade.entry_bar,
            exit_bar_index=bt_trade.exit_bar,
            entry_price=bt_trade.entry_price,
            exit_price=bt_trade.exit_price,
            direction=bt_trade.direction,
            lot_size=lot,
            pnl=bt_trade.pnl,
            pnl_r=round(pnl_r, 4),
            hold_bars=bt_trade.holding_bars,
            exit_reason=bt_trade.exit_reason,
        )


def check_entry_would_trigger(agent: BaseAgent, ctx) -> bool:
    """Check if base entry conditions are met (ignoring calibration).

    Used to count signals that the CalibratedAgent would have skipped.
    """
    from tradememory.evolution.backtester import check_entry
    from tradememory.simulation.agent import CalibratedAgent

    if isinstance(agent, CalibratedAgent):
        # For CalibratedAgent, check raw strategy conditions
        return check_entry(agent.strategy, ctx)
    return False

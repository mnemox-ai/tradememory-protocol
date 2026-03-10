"""
Dashboard service — business logic layer.

Computes derived metrics (win_rate, profit_factor, max_drawdown_pct)
from raw repository data. No direct DB access.
"""

import logging

from ..exceptions import DatabaseConnectionError, DatabaseQueryError
from ..repositories.trade import TradeRepository

logger = logging.getLogger(__name__)


class DashboardService:
    """Business logic for dashboard endpoints."""

    def __init__(self, repo: TradeRepository):
        self._repo = repo

    def get_overview(self) -> dict:
        """
        Compute overview metrics from trade, memory, and equity data.

        Returns a dict matching OverviewResponse schema.
        """
        trade_stats = self._repo.get_trade_stats()
        memory_stats = self._repo.get_memory_stats()
        equity_stats = self._repo.get_equity_stats()

        # Compute derived metrics
        win_rate = 0.0
        if trade_stats.total_trades > 0:
            win_rate = round(trade_stats.win_count / trade_stats.total_trades, 4)

        profit_factor = 0.0
        if trade_stats.gross_loss > 0:
            profit_factor = round(
                trade_stats.gross_profit / trade_stats.gross_loss, 4
            )
        elif trade_stats.gross_profit > 0:
            # All wins, no losses
            profit_factor = float("inf")

        # max_drawdown_pct from affective_state drawdown_state
        max_drawdown_pct = round(equity_stats.drawdown_state * 100, 2)

        return {
            "total_trades": trade_stats.total_trades,
            "total_pnl": round(trade_stats.total_pnl, 2),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "current_equity": round(equity_stats.current_equity, 2),
            "max_drawdown_pct": max_drawdown_pct,
            "memory_count": memory_stats.memory_count,
            "avg_confidence": memory_stats.avg_confidence,
            "last_trade_date": trade_stats.last_trade_date,
            "strategies": trade_stats.strategies,
        }

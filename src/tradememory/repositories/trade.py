"""
Trade repository — data access layer for dashboard.

Tries PostgreSQL first, falls back to SQLite.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from ..db import Database
from ..exceptions import DatabaseConnectionError, DatabaseQueryError

logger = logging.getLogger(__name__)


@dataclass
class TradeStats:
    """Raw trade statistics from the database."""

    total_trades: int = 0
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    strategies: list = None
    last_trade_date: Optional[str] = None

    def __post_init__(self):
        if self.strategies is None:
            self.strategies = []


@dataclass
class MemoryStats:
    """Raw memory statistics from the database."""

    memory_count: int = 0
    avg_confidence: float = 0.0


@dataclass
class EquityStats:
    """Raw equity/drawdown statistics from the database."""

    current_equity: float = 0.0
    peak_equity: float = 0.0
    drawdown_state: float = 0.0


class TradeRepository:
    """Data access layer for trade and memory data."""

    def __init__(self, db: Optional[Database] = None):
        self._db = db

    def _get_db(self) -> Database:
        if self._db is not None:
            return self._db
        try:
            return Database()
        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {e}")
            raise DatabaseConnectionError(f"Cannot connect to database: {e}")

    def get_trade_stats(self) -> TradeStats:
        """Query trade_records for P&L statistics."""
        db = self._get_db()
        conn = db._get_connection()
        try:
            # Aggregate P&L stats from closed trades (pnl IS NOT NULL)
            row = conn.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    COALESCE(SUM(pnl), 0.0) as total_pnl,
                    COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END), 0.0) as gross_profit,
                    COALESCE(ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)), 0.0) as gross_loss,
                    COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as win_count,
                    COALESCE(SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END), 0) as loss_count
                FROM trade_records
                WHERE pnl IS NOT NULL
            """).fetchone()

            # Distinct strategies
            strategy_rows = conn.execute(
                "SELECT DISTINCT strategy FROM trade_records ORDER BY strategy"
            ).fetchall()
            strategies = [r["strategy"] for r in strategy_rows]

            # Last trade date
            last_row = conn.execute(
                "SELECT MAX(timestamp) as last_ts FROM trade_records"
            ).fetchone()
            last_trade_date = last_row["last_ts"] if last_row else None

            return TradeStats(
                total_trades=row["total_trades"],
                total_pnl=row["total_pnl"],
                gross_profit=row["gross_profit"],
                gross_loss=row["gross_loss"],
                win_count=row["win_count"],
                loss_count=row["loss_count"],
                strategies=strategies,
                last_trade_date=last_trade_date,
            )
        except DatabaseConnectionError:
            raise
        except Exception as e:
            logger.error(f"Failed to query trade stats: {e}")
            raise DatabaseQueryError(f"Trade stats query failed: {e}")
        finally:
            conn.close()

    def get_memory_stats(self) -> MemoryStats:
        """Query episodic_memory for memory count and avg confidence."""
        db = self._get_db()
        conn = db._get_connection()
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*) as memory_count,
                    COALESCE(AVG(confidence), 0.0) as avg_confidence
                FROM episodic_memory
            """).fetchone()

            return MemoryStats(
                memory_count=row["memory_count"],
                avg_confidence=round(row["avg_confidence"], 4),
            )
        except Exception as e:
            logger.error(f"Failed to query memory stats: {e}")
            raise DatabaseQueryError(f"Memory stats query failed: {e}")
        finally:
            conn.close()

    def get_equity_stats(self) -> EquityStats:
        """Query affective_state for equity and drawdown."""
        db = self._get_db()
        conn = db._get_connection()
        try:
            row = conn.execute("""
                SELECT current_equity, peak_equity, drawdown_state
                FROM affective_state
                LIMIT 1
            """).fetchone()

            if row is None:
                return EquityStats()

            return EquityStats(
                current_equity=row["current_equity"],
                peak_equity=row["peak_equity"],
                drawdown_state=row["drawdown_state"],
            )
        except Exception as e:
            logger.error(f"Failed to query equity stats: {e}")
            raise DatabaseQueryError(f"Equity stats query failed: {e}")
        finally:
            conn.close()

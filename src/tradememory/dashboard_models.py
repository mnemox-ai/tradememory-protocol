"""
Pydantic response models for dashboard API.
"""

from typing import List, Optional

from pydantic import BaseModel


class OverviewResponse(BaseModel):
    """Response model for GET /dashboard/overview."""

    total_trades: int
    total_pnl: float
    win_rate: float
    profit_factor: float
    current_equity: float
    max_drawdown_pct: float
    memory_count: int
    avg_confidence: float
    last_trade_date: Optional[str] = None
    strategies: List[str] = []

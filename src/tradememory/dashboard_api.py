"""
Dashboard API router — request/response layer only.

All business logic lives in services/dashboard.py.
All data access lives in repositories/trade.py.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from .dashboard_models import OverviewResponse
from .exceptions import DatabaseConnectionError, DatabaseQueryError
from .repositories.trade import TradeRepository
from .services.dashboard import DashboardService

logger = logging.getLogger(__name__)

dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_trade_repository() -> TradeRepository:
    return TradeRepository()


def get_dashboard_service(
    repo: TradeRepository = Depends(get_trade_repository),
) -> DashboardService:
    return DashboardService(repo=repo)


@dashboard_router.get("/overview", response_model=OverviewResponse)
async def overview(
    service: DashboardService = Depends(get_dashboard_service),
):
    """Get dashboard overview with key trading metrics."""
    try:
        return service.get_overview()
    except DatabaseConnectionError as e:
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=503, detail="Database temporarily unavailable"
        )
    except DatabaseQueryError as e:
        logger.error(f"Database query error: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to query trading data"
        )

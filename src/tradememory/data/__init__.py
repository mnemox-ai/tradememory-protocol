"""Platform-agnostic market data layer.

Provides a unified DataSource protocol for fetching OHLCV data
from any exchange or broker (Binance, MT5, etc.).
"""

from src.tradememory.data.models import OHLCV, Timeframe
from src.tradememory.data.protocol import DataSource

__all__ = ["DataSource", "OHLCV", "Timeframe"]

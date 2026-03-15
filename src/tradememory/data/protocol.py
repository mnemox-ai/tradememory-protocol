"""DataSource protocol — the contract all data adapters must implement."""

from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from src.tradememory.data.models import OHLCVSeries, Timeframe


@runtime_checkable
class DataSource(Protocol):
    """Protocol for market data sources.

    Implementations:
        - BinanceDataSource (REST API, local cache)
        - MT5DataSource (CSV export wrapper)
        - CSVDataSource (generic CSV loader)

    All timestamps must be UTC.
    """

    @property
    def name(self) -> str:
        """Human-readable source name (e.g. 'binance', 'mt5')."""
        ...

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        limit: Optional[int] = None,
    ) -> OHLCVSeries:
        """Fetch OHLCV data for a symbol and timeframe.

        Args:
            symbol: Trading pair (e.g. 'BTCUSDT', 'XAUUSD').
            timeframe: Bar timeframe.
            start: Start time (UTC, inclusive).
            end: End time (UTC, inclusive).
            limit: Max bars to return (None = all available).

        Returns:
            OHLCVSeries sorted oldest-first.

        Raises:
            DataSourceError: On network/API/parse errors.
        """
        ...

    async def available_symbols(self) -> list[str]:
        """List symbols available from this source."""
        ...


class DataSourceError(Exception):
    """Base error for data source operations."""

    def __init__(self, source: str, message: str):
        self.source = source
        super().__init__(f"[{source}] {message}")


class RateLimitError(DataSourceError):
    """Rate limit exceeded."""

    def __init__(self, source: str, retry_after: Optional[float] = None):
        self.retry_after = retry_after
        msg = "Rate limit exceeded"
        if retry_after:
            msg += f" (retry after {retry_after}s)"
        super().__init__(source, msg)


class SymbolNotFoundError(DataSourceError):
    """Requested symbol not available."""

    def __init__(self, source: str, symbol: str):
        self.symbol = symbol
        super().__init__(source, f"Symbol '{symbol}' not found")

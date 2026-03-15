"""Binance historical data adapter — implements DataSource Protocol.

Public /klines endpoint, no API key required.
Rate limiting: respects 1200 requests/minute weight limit.
Local parquet cache: ~/.tradememory/cache/binance/
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from src.tradememory.data.models import OHLCV, OHLCVSeries, Timeframe
from src.tradememory.data.protocol import (
    DataSourceError,
    RateLimitError,
    SymbolNotFoundError,
)

logger = logging.getLogger(__name__)

# Binance API constants
BASE_URL = "https://api.binance.com"
KLINES_ENDPOINT = "/api/v3/klines"
EXCHANGE_INFO_ENDPOINT = "/api/v3/exchangeInfo"
MAX_KLINES_PER_REQUEST = 1000  # Binance limit

# Timeframe mapping: our enum -> Binance interval string
TIMEFRAME_MAP = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1w",
}

# Approximate milliseconds per bar (for pagination)
TIMEFRAME_MS = {
    Timeframe.M1: 60_000,
    Timeframe.M5: 300_000,
    Timeframe.M15: 900_000,
    Timeframe.M30: 1_800_000,
    Timeframe.H1: 3_600_000,
    Timeframe.H4: 14_400_000,
    Timeframe.D1: 86_400_000,
    Timeframe.W1: 604_800_000,
}

# Default cache directory
DEFAULT_CACHE_DIR = Path.home() / ".tradememory" / "cache" / "binance"


class BinanceDataSource:
    """Binance historical OHLCV data via public REST API.

    Features:
        - Automatic pagination for large date ranges
        - Simple rate limiting (sleep between requests)
        - Local parquet file cache
        - No API key required (public endpoints only)
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        requests_per_minute: int = 600,  # conservative: half of 1200 limit
        client: Optional[httpx.AsyncClient] = None,
    ):
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self._min_interval = 60.0 / requests_per_minute  # seconds between requests
        self._last_request_time = 0.0
        self._external_client = client is not None
        self._client = client

    @property
    def name(self) -> str:
        return "binance"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._client and not self._external_client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit(self) -> None:
        """Simple rate limiter: sleep if too fast."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    async def _request_klines(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        limit: int = MAX_KLINES_PER_REQUEST,
    ) -> list[list]:
        """Single /klines API call with rate limiting."""
        await self._rate_limit()
        client = await self._get_client()

        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit,
        }

        try:
            resp = await client.get(KLINES_ENDPOINT, params=params)
        except httpx.HTTPError as e:
            raise DataSourceError("binance", f"HTTP error: {e}") from e

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "60"))
            raise RateLimitError("binance", retry_after=retry_after)

        if resp.status_code == 400:
            data = resp.json()
            msg = data.get("msg", "Bad request")
            if "Invalid symbol" in msg:
                raise SymbolNotFoundError("binance", symbol)
            raise DataSourceError("binance", f"API error {resp.status_code}: {msg}")

        if resp.status_code != 200:
            raise DataSourceError(
                "binance", f"Unexpected status {resp.status_code}: {resp.text[:200]}"
            )

        return resp.json()

    def _parse_klines(self, raw: list[list]) -> list[OHLCV]:
        """Parse Binance kline array format into OHLCV models.

        Binance kline format: [open_time, open, high, low, close, volume,
                               close_time, quote_volume, trades, ...]
        """
        bars = []
        for k in raw:
            bars.append(
                OHLCV(
                    timestamp=datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                )
            )
        return bars

    def _cache_key(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> Path:
        """Generate cache file path."""
        s = start.strftime("%Y%m%d")
        e = end.strftime("%Y%m%d")
        return (
            self._cache_dir
            / f"{symbol.upper()}_{timeframe.value}_{s}_{e}.parquet"
        )

    def _load_cache(self, path: Path) -> Optional[OHLCVSeries]:
        """Load cached data from parquet file."""
        if not path.exists():
            return None
        try:
            import pyarrow.parquet as pq

            table = pq.read_table(path)
            df = table.to_pydict()
            bars = []
            for i in range(len(df["timestamp"])):
                bars.append(
                    OHLCV(
                        timestamp=df["timestamp"][i],
                        open=df["open"][i],
                        high=df["high"][i],
                        low=df["low"][i],
                        close=df["close"][i],
                        volume=df["volume"][i],
                    )
                )
            # Extract metadata from filename
            stem = path.stem  # e.g. BTCUSDT_1h_20240101_20260101
            parts = stem.split("_")
            symbol = parts[0]
            tf_str = parts[1]
            tf = Timeframe(tf_str)
            return OHLCVSeries(
                symbol=symbol, timeframe=tf, bars=bars, source="binance"
            )
        except Exception as e:
            logger.warning(f"Cache read failed for {path}: {e}")
            return None

    def _save_cache(self, path: Path, series: OHLCVSeries) -> None:
        """Save data to parquet cache."""
        if not series.bars:
            return
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "timestamp": [b.timestamp for b in series.bars],
                "open": [b.open for b in series.bars],
                "high": [b.high for b in series.bars],
                "low": [b.low for b in series.bars],
                "close": [b.close for b in series.bars],
                "volume": [b.volume for b in series.bars],
            }
            table = pa.table(data)
            pq.write_table(table, path)
            logger.info(f"Cached {len(series.bars)} bars to {path}")
        except Exception as e:
            logger.warning(f"Cache write failed for {path}: {e}")

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        limit: Optional[int] = None,
    ) -> OHLCVSeries:
        """Fetch OHLCV data from Binance with pagination and caching.

        Args:
            symbol: Trading pair (e.g. 'BTCUSDT').
            timeframe: Bar timeframe.
            start: Start time (UTC, inclusive).
            end: End time (UTC, inclusive).
            limit: Max bars to return (None = all available).

        Returns:
            OHLCVSeries sorted oldest-first.
        """
        # Check cache first
        cache_path = self._cache_key(symbol, timeframe, start, end)
        cached = self._load_cache(cache_path)
        if cached is not None:
            logger.info(f"Cache hit: {cache_path.name} ({cached.count} bars)")
            if limit:
                cached.bars = cached.bars[:limit]
            return cached

        # Pagination: fetch in chunks of 1000
        interval = TIMEFRAME_MAP[timeframe]
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        bar_ms = TIMEFRAME_MS[timeframe]

        all_bars: list[OHLCV] = []
        current_start = start_ms

        while current_start < end_ms:
            raw = await self._request_klines(
                symbol=symbol,
                interval=interval,
                start_ms=current_start,
                end_ms=end_ms,
            )

            if not raw:
                break

            bars = self._parse_klines(raw)
            all_bars.extend(bars)

            if limit and len(all_bars) >= limit:
                all_bars = all_bars[:limit]
                break

            # Move start to after last received bar
            last_open_ms = raw[-1][0]
            current_start = last_open_ms + bar_ms

            # If we got fewer than max, we're done
            if len(raw) < MAX_KLINES_PER_REQUEST:
                break

        series = OHLCVSeries(
            symbol=symbol.upper(),
            timeframe=timeframe,
            bars=all_bars,
            source="binance",
        )

        # Cache the result
        if all_bars and not limit:
            self._save_cache(cache_path, series)

        logger.info(
            f"Fetched {len(all_bars)} bars for {symbol} {timeframe.value} "
            f"from Binance ({start.date()} to {end.date()})"
        )
        return series

    async def available_symbols(self) -> list[str]:
        """List all trading pairs on Binance."""
        await self._rate_limit()
        client = await self._get_client()

        try:
            resp = await client.get(EXCHANGE_INFO_ENDPOINT)
        except httpx.HTTPError as e:
            raise DataSourceError("binance", f"HTTP error: {e}") from e

        if resp.status_code != 200:
            raise DataSourceError(
                "binance", f"exchangeInfo failed: {resp.status_code}"
            )

        data = resp.json()
        return [s["symbol"] for s in data.get("symbols", []) if s.get("status") == "TRADING"]

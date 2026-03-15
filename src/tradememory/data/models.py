"""Shared data models for the market data layer."""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Timeframe(str, Enum):
    """Supported OHLCV timeframes."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class OHLCV(BaseModel):
    """Single OHLCV bar, exchange-agnostic.

    All timestamps are UTC. Volume is base asset volume (not quote).
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: datetime) -> datetime:
        """Ensure timestamp has UTC timezone info."""
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def high_gte_low(self) -> "OHLCV":
        """High must be >= low."""
        if self.high < self.low:
            raise ValueError(
                f"high ({self.high}) must be >= low ({self.low})"
            )
        return self

    @property
    def mid(self) -> float:
        """Mid price = (high + low) / 2."""
        return (self.high + self.low) / 2.0

    @property
    def range(self) -> float:
        """Bar range = high - low."""
        return self.high - self.low

    @property
    def body(self) -> float:
        """Candle body = close - open (positive = bullish)."""
        return self.close - self.open

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


class OHLCVSeries(BaseModel):
    """A series of OHLCV bars with metadata."""

    symbol: str
    timeframe: Timeframe
    bars: List[OHLCV] = Field(default_factory=list)
    source: str = ""  # e.g. "binance", "mt5_csv"

    @property
    def start(self) -> Optional[datetime]:
        return self.bars[0].timestamp if self.bars else None

    @property
    def end(self) -> Optional[datetime]:
        return self.bars[-1].timestamp if self.bars else None

    @property
    def count(self) -> int:
        return len(self.bars)

    def slice(self, start: datetime, end: datetime) -> "OHLCVSeries":
        """Return a new series filtered to [start, end]."""
        filtered = [b for b in self.bars if start <= b.timestamp <= end]
        return OHLCVSeries(
            symbol=self.symbol,
            timeframe=self.timeframe,
            bars=filtered,
            source=self.source,
        )

    def split(self, ratio: float = 0.7) -> tuple["OHLCVSeries", "OHLCVSeries"]:
        """Split into in-sample / out-of-sample by ratio.

        Args:
            ratio: Fraction for in-sample (default 0.7 = 70% IS, 30% OOS).

        Returns:
            (in_sample, out_of_sample) tuple.
        """
        if not self.bars:
            empty = OHLCVSeries(
                symbol=self.symbol,
                timeframe=self.timeframe,
                bars=[],
                source=self.source,
            )
            return empty, empty

        split_idx = int(len(self.bars) * ratio)
        split_idx = max(1, min(split_idx, len(self.bars) - 1))

        return (
            OHLCVSeries(
                symbol=self.symbol,
                timeframe=self.timeframe,
                bars=self.bars[:split_idx],
                source=self.source,
            ),
            OHLCVSeries(
                symbol=self.symbol,
                timeframe=self.timeframe,
                bars=self.bars[split_idx:],
                source=self.source,
            ),
        )

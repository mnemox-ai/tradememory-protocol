"""Context Builder — compute ContextVector from OHLCVSeries.

Aligned with P1 experiment findings:
- Strategy C (US Session Drain): 16:00 UTC short
- Strategy E (Afternoon Engine): 14:00 UTC long + 12H trend filter
- Edge comes from time-slot + trend direction combos

Key design:
- Pure functions, no external state
- Multi-timeframe ATR (D1, H4, H1)
- Trend direction + magnitude at 12H and 24H scales
- Hour-level session granularity (not just asia/london/newyork)
- Volatility regime via ATR percentile rank
- Regime classification via configurable method (price_vs_sma or adx)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Sequence

from tradememory.data.models import OHLCV, OHLCVSeries


# --- Enums ---

class Regime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"


class VolatilityRegime(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class Session(str, Enum):
    ASIA = "asia"
    LONDON = "london"
    NEWYORK = "newyork"
    OVERLAP = "overlap"  # London + NY overlap (13:00-16:00 UTC)


class RegimeMethod(str, Enum):
    """Regime classification method — configurable per Sean's spec."""
    PRICE_VS_SMA = "price_vs_sma"
    ADX = "adx"


# --- Config ---

@dataclass
class ContextConfig:
    """Configurable parameters for context computation."""

    # ATR periods
    atr_period: int = 14

    # Regime classification
    regime_method: RegimeMethod = RegimeMethod.PRICE_VS_SMA
    sma_period: int = 20  # for price_vs_sma method
    adx_period: int = 14  # for adx method
    adx_trend_threshold: float = 25.0  # ADX > this = trending
    ranging_body_ratio: float = 0.3  # avg |body|/range < this = ranging

    # Volatility regime percentile thresholds
    vol_lookback: int = 60  # bars to compute percentile rank
    vol_low_pct: float = 25.0
    vol_normal_pct: float = 75.0
    vol_extreme_pct: float = 95.0

    # Trend magnitude lookback (in bars, not hours — caller converts)
    trend_12h_bars: int = 12  # for H1 data = 12 bars
    trend_24h_bars: int = 24  # for H1 data = 24 bars


# --- MarketContext (extended ContextVector) ---

@dataclass
class MarketContext:
    """Computed market context from OHLCV data.

    Extends the OWM ContextVector with P1-aligned fields:
    - hour_utc for precise time-slot strategies
    - trend_12h / trend_24h for multi-scale trend filters
    - atr_h4 for intermediate timeframe
    """

    # Timestamp
    timestamp: Optional[datetime] = None
    hour_utc: Optional[int] = None
    day_of_week: Optional[int] = None  # 0=Mon, 6=Sun

    # Session
    session: Optional[Session] = None

    # ATR multi-timeframe (in price units, e.g. dollars)
    atr_d1: Optional[float] = None
    atr_h4: Optional[float] = None
    atr_h1: Optional[float] = None
    atr_ratio_h1_d1: Optional[float] = None

    # Regime
    regime: Optional[Regime] = None
    volatility_regime: Optional[VolatilityRegime] = None
    atr_percentile: Optional[float] = None  # 0-100

    # Trend direction + magnitude (P1 core filters)
    trend_12h: Optional[float] = None  # price change over 12H (absolute)
    trend_12h_pct: Optional[float] = None  # price change over 12H (%)
    trend_24h: Optional[float] = None  # price change over 24H (absolute)
    trend_24h_pct: Optional[float] = None  # price change over 24H (%)

    # Price
    price: Optional[float] = None
    symbol: Optional[str] = None

    def to_owm_context(self):
        """Convert to OWM ContextVector for recall compatibility."""
        from tradememory.owm.context import ContextVector

        return ContextVector(
            symbol=self.symbol,
            price=self.price,
            atr_d1=self.atr_d1,
            atr_h1=self.atr_h1,
            atr_m5=None,  # not computed here
            atr_ratio_h1_d1=self.atr_ratio_h1_d1,
            regime=self.regime.value if self.regime else None,
            volatility_regime=self.volatility_regime.value if self.volatility_regime else None,
            session=self.session.value if self.session else None,
            hour_utc=self.hour_utc,
            day_of_week=self.day_of_week,
        )


# --- Pure computation functions ---


def compute_atr(bars: Sequence[OHLCV], period: int = 14) -> Optional[float]:
    """Compute Average True Range over `period` bars.

    Uses Wilder's smoothing (EMA with alpha = 1/period).
    Requires at least `period + 1` bars.
    """
    if len(bars) < period + 1:
        return None

    # True Range for each bar (skip first — no previous close)
    true_ranges = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        current = bars[i]
        tr = max(
            current.high - current.low,
            abs(current.high - prev_close),
            abs(current.low - prev_close),
        )
        true_ranges.append(tr)

    # Wilder's smoothing: initial ATR = SMA of first `period` TRs
    if len(true_ranges) < period:
        return None

    atr = sum(true_ranges[:period]) / period

    # Then EMA for remaining
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period

    return atr


def compute_sma(values: Sequence[float], period: int) -> Optional[float]:
    """Simple Moving Average of last `period` values."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def compute_adx(bars: Sequence[OHLCV], period: int = 14) -> Optional[float]:
    """Compute Average Directional Index (ADX).

    Returns ADX value (0-100). Requires at least 2*period + 1 bars.
    """
    if len(bars) < 2 * period + 1:
        return None

    plus_dm_list = []
    minus_dm_list = []
    tr_list = []

    for i in range(1, len(bars)):
        high_diff = bars[i].high - bars[i - 1].high
        low_diff = bars[i - 1].low - bars[i].low

        plus_dm = max(high_diff, 0) if high_diff > low_diff else 0
        minus_dm = max(low_diff, 0) if low_diff > high_diff else 0

        prev_close = bars[i - 1].close
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - prev_close),
            abs(bars[i].low - prev_close),
        )

        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)
        tr_list.append(tr)

    if len(tr_list) < 2 * period:
        return None

    # Wilder's smoothing for +DM, -DM, TR
    def wilder_smooth(data: list[float], p: int) -> list[float]:
        result = [sum(data[:p]) / p]
        for v in data[p:]:
            result.append((result[-1] * (p - 1) + v) / p)
        return result

    smoothed_tr = wilder_smooth(tr_list, period)
    smoothed_plus = wilder_smooth(plus_dm_list, period)
    smoothed_minus = wilder_smooth(minus_dm_list, period)

    # DI+ and DI-
    dx_list = []
    for i in range(len(smoothed_tr)):
        tr_val = smoothed_tr[i]
        if tr_val == 0:
            dx_list.append(0)
            continue
        plus_di = 100 * smoothed_plus[i] / tr_val
        minus_di = 100 * smoothed_minus[i] / tr_val
        di_sum = plus_di + minus_di
        if di_sum == 0:
            dx_list.append(0)
        else:
            dx_list.append(100 * abs(plus_di - minus_di) / di_sum)

    if len(dx_list) < period:
        return None

    # ADX = Wilder's smoothing of DX
    adx_values = wilder_smooth(dx_list, period)
    return adx_values[-1] if adx_values else None


def classify_session(hour_utc: int) -> Session:
    """Classify trading session by UTC hour.

    Sessions (approximate):
    - Asia: 00:00-07:00 UTC (Tokyo 09:00-16:00 JST)
    - London: 07:00-13:00 UTC (London 08:00-14:00 BST)
    - Overlap: 13:00-16:00 UTC (London + NY)
    - New York: 16:00-21:00 UTC (NY 12:00-17:00 EST)
    - Late/Asia prep: 21:00-00:00 UTC → classified as Asia
    """
    if 0 <= hour_utc < 7:
        return Session.ASIA
    elif 7 <= hour_utc < 13:
        return Session.LONDON
    elif 13 <= hour_utc < 16:
        return Session.OVERLAP
    elif 16 <= hour_utc < 21:
        return Session.NEWYORK
    else:  # 21-23
        return Session.ASIA


def classify_regime(
    bars: Sequence[OHLCV],
    config: ContextConfig = ContextConfig(),
) -> Regime:
    """Classify market regime from recent bars.

    Methods:
    - price_vs_sma: price vs SMA direction + body analysis
    - adx: ADX-based trending detection
    """
    if len(bars) < max(config.sma_period, config.adx_period) + 1:
        return Regime.RANGING  # not enough data

    if config.regime_method == RegimeMethod.ADX:
        return _classify_regime_adx(bars, config)
    else:
        return _classify_regime_sma(bars, config)


def _classify_regime_sma(bars: Sequence[OHLCV], config: ContextConfig) -> Regime:
    """Regime via price vs SMA + body analysis."""
    closes = [b.close for b in bars]
    sma = compute_sma(closes, config.sma_period)
    if sma is None:
        return Regime.RANGING

    current_price = closes[-1]
    price_vs_sma = (current_price - sma) / sma  # fractional distance

    # Check if volatile: large ranges with small bodies = indecision
    recent = bars[-config.sma_period:]
    avg_range = sum(b.range for b in recent) / len(recent) if recent else 0
    avg_body = sum(abs(b.body) for b in recent) / len(recent) if recent else 0
    body_ratio = avg_body / avg_range if avg_range > 0 else 0

    if body_ratio < config.ranging_body_ratio:
        # Small bodies relative to range = choppy/volatile
        # But check ATR expansion for volatile vs ranging
        atr = compute_atr(list(bars), config.atr_period)
        if atr and avg_range > 1.5 * atr:
            return Regime.VOLATILE
        return Regime.RANGING

    # Trending threshold: price > 1% above/below SMA
    if price_vs_sma > 0.01:
        return Regime.TRENDING_UP
    elif price_vs_sma < -0.01:
        return Regime.TRENDING_DOWN
    else:
        return Regime.RANGING


def _classify_regime_adx(bars: Sequence[OHLCV], config: ContextConfig) -> Regime:
    """Regime via ADX + price direction."""
    adx = compute_adx(list(bars), config.adx_period)
    if adx is None:
        return Regime.RANGING

    if adx < config.adx_trend_threshold:
        # Low ADX — check for volatile vs ranging
        recent = bars[-config.sma_period:]
        avg_range = sum(b.range for b in recent) / len(recent) if recent else 0
        atr = compute_atr(list(bars), config.atr_period)
        if atr and avg_range > 1.5 * atr:
            return Regime.VOLATILE
        return Regime.RANGING

    # Trending — determine direction from recent price change
    lookback = min(config.sma_period, len(bars))
    price_change = bars[-1].close - bars[-lookback].close
    if price_change > 0:
        return Regime.TRENDING_UP
    else:
        return Regime.TRENDING_DOWN


def classify_volatility(
    current_atr: float,
    bars: Sequence[OHLCV],
    config: ContextConfig = ContextConfig(),
) -> tuple[VolatilityRegime, float]:
    """Classify volatility regime via ATR percentile rank.

    Returns (regime, percentile_rank 0-100).
    """
    lookback = min(config.vol_lookback, len(bars))
    if lookback < config.atr_period + 2:
        return VolatilityRegime.NORMAL, 50.0

    # Compute ATR for each position in the lookback window
    atr_values = []
    for i in range(config.atr_period + 1, lookback + 1):
        window = bars[-i:][:config.atr_period + 1]
        if len(window) >= config.atr_period + 1:
            atr = compute_atr(window, config.atr_period)
            if atr is not None:
                atr_values.append(atr)

    if not atr_values:
        return VolatilityRegime.NORMAL, 50.0

    # Percentile rank: % of historical ATRs that current ATR exceeds
    count_below = sum(1 for a in atr_values if a < current_atr)
    percentile = (count_below / len(atr_values)) * 100

    if percentile <= config.vol_low_pct:
        regime = VolatilityRegime.LOW
    elif percentile <= config.vol_normal_pct:
        regime = VolatilityRegime.NORMAL
    elif percentile <= config.vol_extreme_pct:
        regime = VolatilityRegime.HIGH
    else:
        regime = VolatilityRegime.EXTREME

    return regime, percentile


def compute_trend(
    bars: Sequence[OHLCV], lookback_bars: int
) -> tuple[Optional[float], Optional[float]]:
    """Compute trend direction + magnitude over lookback_bars.

    Returns (absolute_change, pct_change).
    """
    if len(bars) < lookback_bars + 1:
        return None, None

    current = bars[-1].close
    past = bars[-(lookback_bars + 1)].close

    if past == 0:
        return None, None

    absolute = current - past
    pct = (absolute / past) * 100

    return absolute, pct


# --- Main builder ---


def build_context(
    series: OHLCVSeries,
    bar_index: int = -1,
    config: Optional[ContextConfig] = None,
    h4_series: Optional[OHLCVSeries] = None,
    d1_series: Optional[OHLCVSeries] = None,
) -> MarketContext:
    """Build MarketContext from OHLCVSeries at a specific bar.

    Args:
        series: Primary OHLCV data (typically H1).
        bar_index: Which bar to compute context for (-1 = last).
        config: Configuration parameters.
        h4_series: Optional H4 data for multi-timeframe ATR.
        d1_series: Optional D1 data for multi-timeframe ATR.

    Returns:
        MarketContext with all computable fields filled.
    """
    if config is None:
        config = ContextConfig()

    if not series.bars:
        return MarketContext(symbol=series.symbol)

    # Resolve bar_index
    if bar_index < 0:
        bar_index = len(series.bars) + bar_index
    if bar_index < 0 or bar_index >= len(series.bars):
        return MarketContext(symbol=series.symbol)

    # Slice up to and including the target bar
    bars_up_to = series.bars[: bar_index + 1]
    current_bar = bars_up_to[-1]

    ctx = MarketContext(
        symbol=series.symbol,
        price=current_bar.close,
        timestamp=current_bar.timestamp,
    )

    # Time fields
    ts = current_bar.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ctx.hour_utc = ts.hour
    ctx.day_of_week = ts.weekday()
    ctx.session = classify_session(ts.hour)

    # ATR H1 (primary series)
    ctx.atr_h1 = compute_atr(bars_up_to, config.atr_period)

    # ATR H4
    if h4_series and h4_series.bars:
        h4_bars = [b for b in h4_series.bars if b.timestamp <= current_bar.timestamp]
        if h4_bars:
            ctx.atr_h4 = compute_atr(h4_bars, config.atr_period)

    # ATR D1
    if d1_series and d1_series.bars:
        d1_bars = [b for b in d1_series.bars if b.timestamp <= current_bar.timestamp]
        if d1_bars:
            ctx.atr_d1 = compute_atr(d1_bars, config.atr_period)

    # ATR ratio
    if ctx.atr_h1 and ctx.atr_d1 and ctx.atr_d1 > 0:
        ctx.atr_ratio_h1_d1 = ctx.atr_h1 / ctx.atr_d1

    # Regime
    ctx.regime = classify_regime(bars_up_to, config)

    # Volatility regime
    if ctx.atr_h1 is not None:
        vol_regime, pct = classify_volatility(ctx.atr_h1, bars_up_to, config)
        ctx.volatility_regime = vol_regime
        ctx.atr_percentile = round(pct, 1)

    # Trend 12H and 24H (P1 core filters)
    ctx.trend_12h, ctx.trend_12h_pct = compute_trend(bars_up_to, config.trend_12h_bars)
    ctx.trend_24h, ctx.trend_24h_pct = compute_trend(bars_up_to, config.trend_24h_bars)

    return ctx

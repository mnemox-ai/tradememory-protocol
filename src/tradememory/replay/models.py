"""Pydantic models for the LLM Trading Agent Replay Engine."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional, List

from pydantic import BaseModel, Field, field_validator


VALID_STRATEGIES = ["VolBreakout", "IntradayMomentum", "PullbackEntry", "NONE"]

# Map common LLM abbreviations/variations to canonical names
_STRATEGY_ALIASES: dict[str, str] = {
    "VB": "VolBreakout",
    "vb": "VolBreakout",
    "volbreakout": "VolBreakout",
    "vol_breakout": "VolBreakout",
    "IM": "IntradayMomentum",
    "im": "IntradayMomentum",
    "intradaymomentum": "IntradayMomentum",
    "intraday_momentum": "IntradayMomentum",
    "PB": "PullbackEntry",
    "pb": "PullbackEntry",
    "pullbackentry": "PullbackEntry",
    "pullback_entry": "PullbackEntry",
    "NONE": "NONE",
    "none": "NONE",
    "None": "NONE",
    "null": "NONE",
}


class Bar(BaseModel):
    """Single 15-min OHLCV bar from MT5 CSV export."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    spread: int = 0


class IndicatorSnapshot(BaseModel):
    """Computed indicators at a point in time.

    Multi-timeframe ATR requires sufficient data:
    - ATR(14, M15): needs 15 M15 bars (~4 hours)
    - ATR(14, H1): needs 15 H1 bars = 60 M15 bars (~15 hours)
    - ATR(14, D1): needs 15 D1 bars = 1440 M15 bars (~15 trading days)
    None means insufficient data.
    """

    atr_d1: Optional[float] = None
    atr_h1: Optional[float] = None
    atr_m15: Optional[float] = None
    rsi_14: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None


class DecisionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


class AgentDecision(BaseModel):
    """Structured output from LLM agent. One per decision point."""

    market_observation: str = Field(
        ..., description="What the agent observes in current market state"
    )
    reasoning_trace: str = Field(
        ..., description="Step-by-step reasoning chain leading to decision"
    )
    decision: DecisionType
    confidence: float = Field(..., ge=0.0, le=1.0)
    strategy_used: Optional[str] = Field(
        None,
        description="VolBreakout, IntradayMomentum, PullbackEntry, or null for HOLD",
    )

    @field_validator("strategy_used", mode="before")
    @classmethod
    def normalize_strategy(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_stripped = v.strip()
        # Direct match
        if v_stripped in VALID_STRATEGIES:
            return v_stripped
        # Alias lookup
        if v_stripped in _STRATEGY_ALIASES:
            return _STRATEGY_ALIASES[v_stripped]
        # Multi-strategy string: pick the first valid one
        for sep in [",", "/", " and ", "&"]:
            if sep in v_stripped:
                first = v_stripped.split(sep)[0].strip()
                if first in VALID_STRATEGIES:
                    return first
                if first in _STRATEGY_ALIASES:
                    return _STRATEGY_ALIASES[first]
        # Case-insensitive fallback
        lower = v_stripped.lower()
        if lower in _STRATEGY_ALIASES:
            return _STRATEGY_ALIASES[lower]
        # Unknown strategy — return as-is (don't crash)
        return v_stripped

    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class PositionState(str, Enum):
    OPEN = "open"
    CLOSED_TP = "closed_tp"
    CLOSED_SL = "closed_sl"
    CLOSED_EOD = "closed_eod"
    CLOSED_AGENT = "closed_agent"


class Position(BaseModel):
    """Tracks a single position from open to close."""

    trade_id: str
    direction: str  # "long" or "short"
    strategy: str
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    confidence: float
    reasoning: str
    market_observation: str = ""
    # Filled on close
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl: Optional[float] = None  # dollar PnL (1 lot = 100 oz for XAUUSD)
    pnl_r: Optional[float] = None  # R-multiple
    state: PositionState = PositionState.OPEN
    max_adverse_excursion: float = 0.0
    bars_held: int = 0


class ReplayConfig(BaseModel):
    """Configuration for a replay run."""

    data_path: str
    symbol: str = "XAUUSD"

    # LLM settings
    llm_provider: str = "deepseek"  # "deepseek" or "claude"
    llm_model: Optional[str] = None  # auto-selected if None
    api_key_env: str = "DEEPSEEK_API_KEY"  # env var name

    # Replay parameters
    window_size: int = 96  # bars visible to agent (96 = 24h of M15)
    decision_interval: int = 4  # decide every N bars (4 = every hour)
    lot_size: float = 0.10
    initial_equity: float = 10000.0
    max_positions: int = 1

    # Storage
    store_to_memory: bool = True
    db_path: str = "data/replay.db"

    # Memory recall
    use_memory_recall: bool = False
    # Pluggable memory recall function: (db_path, strategy, regime, session, atr_d1) -> str
    # If set, overrides the built-in build_memory_context when use_memory_recall=True
    memory_recall_fn: Optional[Any] = None

    # Pluggable strategy prompt — override the built-in generic prompt
    # with your own strategy rules (e.g. from trade-dreaming package)
    system_prompt: Optional[str] = None

    # Resumability
    resume_from_bar: int = 0
    max_decisions: int = 0  # 0 = unlimited, useful for cost control

    # Output
    log_path: Optional[str] = "data/replay_decisions.jsonl"  # JSONL output path

    # Broker time offset from UTC (FXTM: +2 winter, +3 summer)
    broker_utc_offset: int = 2

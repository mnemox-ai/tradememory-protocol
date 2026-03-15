"""Evolution Engine data models.

CandidatePattern: Structured output from LLM pattern discovery.
Hypothesis: A testable trading strategy with entry/exit rules.
FitnessMetrics: Backtest results for a hypothesis.
EvolutionRun: One complete evolution cycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# --- Entry/Exit Condition Schema ---


class ConditionOperator(str, Enum):
    """Operators for rule conditions."""
    GT = "gt"           # >
    GTE = "gte"         # >=
    LT = "lt"           # <
    LTE = "lte"         # <=
    EQ = "eq"           # ==
    NEQ = "neq"         # !=
    BETWEEN = "between" # min <= x <= max
    IN = "in"           # x in [values]


class RuleCondition(BaseModel):
    """Single condition in a trading rule.

    Examples:
        {"field": "hour_utc", "op": "eq", "value": 16}
        {"field": "trend_12h_pct", "op": "lt", "value": 0}
        {"field": "atr_percentile", "op": "between", "value": [25, 75]}
    """
    field: str
    op: ConditionOperator
    value: Any  # float, int, str, list (for BETWEEN/IN)


class EntryCondition(BaseModel):
    """Programmable entry rules for a pattern.

    All conditions must be true (AND logic).
    For OR logic, use multiple CandidatePatterns.
    """
    direction: str = "long"  # "long" or "short"
    conditions: List[RuleCondition] = Field(default_factory=list)
    description: str = ""  # human-readable summary


class ExitCondition(BaseModel):
    """Exit rules: SL, TP, and time-based."""
    stop_loss_atr: Optional[float] = None  # SL as ATR multiple (e.g. 1.5)
    take_profit_atr: Optional[float] = None  # TP as ATR multiple (e.g. 3.0)
    max_holding_bars: Optional[int] = None  # time-based exit
    trailing_stop_atr: Optional[float] = None  # trailing SL as ATR multiple


class ValidityConditions(BaseModel):
    """When this pattern is valid / should be applied."""
    regime: Optional[str] = None  # None = any regime
    volatility_regime: Optional[str] = None
    session: Optional[str] = None
    min_atr_d1: Optional[float] = None
    max_atr_d1: Optional[float] = None
    min_trend_12h_pct: Optional[float] = None
    max_trend_12h_pct: Optional[float] = None


# --- Core Models ---


class CandidatePattern(BaseModel):
    """Structured output from LLM pattern discovery.

    This replaces the P1 free-text patterns (呼吸、巨浪、潮汐...)
    with a JSON schema that can be stored in semantic_memory
    and fed directly to the backtester.
    """
    pattern_id: str = Field(default_factory=lambda: f"PAT-{uuid.uuid4().hex[:6].upper()}")
    name: str
    description: str
    entry_condition: EntryCondition
    exit_condition: ExitCondition = Field(default_factory=ExitCondition)
    validity_conditions: ValidityConditions = Field(default_factory=ValidityConditions)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sample_count: int = 0  # how many bars/trades LLM based this on
    source: str = "llm_discovery"  # "llm_discovery", "manual", "mutation"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at", mode="before")
    @classmethod
    def ensure_utc(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    def to_semantic_memory(self) -> dict:
        """Convert to format suitable for OWM semantic_memory storage."""
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "description": self.description,
            "entry_rules": self.entry_condition.model_dump(),
            "exit_rules": self.exit_condition.model_dump(),
            "validity": self.validity_conditions.model_dump(),
            "confidence": self.confidence,
            "sample_count": self.sample_count,
            "source": self.source,
        }


class FitnessMetrics(BaseModel):
    """Backtest results for evaluating a hypothesis."""

    sharpe_ratio: float = 0.0
    win_rate: float = 0.0  # 0-1
    profit_factor: float = 0.0  # gross_profit / gross_loss
    total_pnl: float = 0.0
    max_drawdown_pct: float = 0.0  # 0-100
    trade_count: int = 0
    avg_trade_pnl: float = 0.0
    avg_holding_bars: float = 0.0
    expectancy: float = 0.0  # avg win * win_rate - avg loss * loss_rate
    consecutive_losses_max: int = 0

    @property
    def is_viable(self) -> bool:
        """Minimum viability: enough trades + positive expectancy."""
        return self.trade_count >= 30 and self.sharpe_ratio > 0

    @property
    def passes_oos_filter(self) -> bool:
        """OOS validation thresholds from ROADMAP."""
        return (
            self.sharpe_ratio > 1.0
            and self.trade_count >= 30
            and self.max_drawdown_pct < 20.0
        )


class HypothesisStatus(str, Enum):
    PENDING = "pending"
    BACKTESTING = "backtesting"
    SURVIVED_IS = "survived_is"
    SURVIVED_OOS = "survived_oos"
    ELIMINATED = "eliminated"
    GRADUATED = "graduated"  # → promoted to semantic_memory


class Hypothesis(BaseModel):
    """A testable trading strategy = CandidatePattern + fitness results.

    Lifecycle: pending → backtesting → survived_is → survived_oos → graduated
                                    → eliminated (at any stage)
    """
    hypothesis_id: str = Field(default_factory=lambda: f"HYP-{uuid.uuid4().hex[:6].upper()}")
    pattern: CandidatePattern
    generation: int = 0  # which evolution generation produced this
    status: HypothesisStatus = HypothesisStatus.PENDING

    # Fitness results (filled after backtesting)
    fitness_is: Optional[FitnessMetrics] = None  # in-sample
    fitness_oos: Optional[FitnessMetrics] = None  # out-of-sample

    # Elimination reason (if eliminated)
    elimination_reason: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at", mode="before")
    @classmethod
    def ensure_utc(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    def to_graveyard_entry(self) -> dict:
        """Convert to Strategy Graveyard format for learning."""
        return {
            "hypothesis_id": self.hypothesis_id,
            "pattern_name": self.pattern.name,
            "description": self.pattern.description,
            "entry_rules": self.pattern.entry_condition.model_dump(),
            "fitness_is": self.fitness_is.model_dump() if self.fitness_is else None,
            "fitness_oos": self.fitness_oos.model_dump() if self.fitness_oos else None,
            "elimination_reason": self.elimination_reason,
            "generation": self.generation,
        }


class EvolutionConfig(BaseModel):
    """Configuration for one evolution run."""
    symbol: str = "BTCUSDT"
    timeframe: str = "1h"
    generations: int = 3
    population_size: int = 10  # hypotheses per generation
    is_oos_ratio: float = 0.7  # 70% IS, 30% OOS
    temperature: float = 0.7  # LLM sampling temperature
    model: Optional[str] = None  # LLM model override


class EvolutionRun(BaseModel):
    """One complete evolution cycle with results."""
    run_id: str = Field(default_factory=lambda: f"EVO-{uuid.uuid4().hex[:6].upper()}")
    config: EvolutionConfig
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    # Results
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    graduated: List[Hypothesis] = Field(default_factory=list)  # survived OOS
    graveyard: List[Hypothesis] = Field(default_factory=list)  # eliminated

    # Stats
    total_llm_tokens: int = 0
    total_backtests: int = 0

    @field_validator("started_at", mode="before")
    @classmethod
    def ensure_utc(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @property
    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "symbol": self.config.symbol,
            "generations": self.config.generations,
            "total_hypotheses": len(self.hypotheses),
            "graduated": len(self.graduated),
            "eliminated": len(self.graveyard),
            "total_llm_tokens": self.total_llm_tokens,
            "total_backtests": self.total_backtests,
        }

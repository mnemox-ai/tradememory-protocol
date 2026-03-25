"""Trading Decision Record (TDR) — MiFID II / EU AI Act inspired audit schema.

Provides a complete, tamper-evident record of every trading decision made by
an AI agent, including the memory context that informed the decision.
"""

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field


class MemoryContext(BaseModel):
    """Memory layer context consulted at decision time."""
    similar_trades: List[str] = Field(
        default_factory=list,
        description="IDs of similar historical trades retrieved via OWM recall",
    )
    relevant_beliefs: List[str] = Field(
        default_factory=list,
        description="Semantic memory propositions consulted (L2 beliefs)",
    )
    anti_resonance_applied: bool = Field(
        default=False,
        description="Whether ensure_negative_balance() was invoked",
    )
    negative_ratio: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description="Fraction of negative memories in recall result",
    )
    recall_count: int = Field(
        default=0,
        description="Number of memories retrieved in recall",
    )


class RiskSnapshot(BaseModel):
    """Risk parameters at decision time."""
    position_size: Optional[float] = None
    risk_per_trade: Optional[float] = Field(
        default=None, description="Risk in account currency (SL distance * lots * contract)"
    )
    risk_percent: Optional[float] = Field(
        default=None, description="Risk as % of account equity"
    )
    max_loss_points: Optional[float] = Field(
        default=None, description="SL distance in price points"
    )


class MarketSnapshot(BaseModel):
    """Market state at decision time."""
    price: Optional[float] = None
    session: Optional[str] = None
    regime: Optional[str] = None
    atr_m5: Optional[float] = None
    atr_h1: Optional[float] = None
    atr_d1: Optional[float] = None
    spread_points: Optional[int] = None
    ema_fast_h1: Optional[float] = None
    ema_slow_h1: Optional[float] = None


class TradingDecisionRecord(BaseModel):
    """Complete audit record for a single trading decision.

    Inspired by:
    - MiFID II Article 17: algorithmic trading record-keeping
    - EU AI Act Article 14: human oversight of high-risk AI systems

    Every field is immutable after creation. The data_hash provides
    tamper detection — recompute and compare to verify integrity.
    """

    # --- Identity ---
    record_id: str = Field(..., description="Unique, immutable (matches trade_id)")
    timestamp: datetime = Field(..., description="Decision timestamp (UTC)")
    agent_id: str = Field(default="mt5_sync_v3", description="Which agent/EA made this decision")
    model_version: str = Field(default="0.5.0", description="TradeMemory version at decision time")

    # --- Decision ---
    decision_type: str = Field(
        ..., description="ENTRY | EXIT | HOLD | SKIP",
        pattern="^(ENTRY|EXIT|HOLD|SKIP)$",
    )
    symbol: str
    direction: Optional[str] = Field(default=None, description="long | short")
    strategy: str

    # --- Context (WHY) ---
    signal_source: str = Field(
        default="", description="What triggered the decision (e.g., 'VolBreakout bar confirmed')"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Agent confidence at decision time"
    )
    market: MarketSnapshot = Field(default_factory=MarketSnapshot)

    # --- Memory (WHAT informed this) ---
    memory: MemoryContext = Field(default_factory=MemoryContext)

    # --- Risk ---
    risk: RiskSnapshot = Field(default_factory=RiskSnapshot)

    # --- Outcome (filled on exit) ---
    exit_timestamp: Optional[datetime] = None
    exit_reason: Optional[str] = Field(
        default=None, description="SL | TP | TIMEOUT | MANUAL | EA_CLOSE"
    )
    pnl: Optional[float] = None
    pnl_r: Optional[float] = None
    hold_duration_minutes: Optional[int] = None

    # --- Audit ---
    data_hash: str = Field(
        default="",
        description="SHA256 of input features at decision time (tamper detection)",
    )

    @staticmethod
    def compute_hash(
        trade_id: str,
        timestamp: str,
        symbol: str,
        direction: str,
        strategy: str,
        confidence: float,
        reasoning: str,
        market_context: Any,
    ) -> str:
        """Compute deterministic SHA256 hash of decision inputs.

        Call this at record creation time and store the result.
        To verify integrity later, recompute and compare.
        """
        payload = json.dumps(
            {
                "trade_id": trade_id,
                "timestamp": str(timestamp),
                "symbol": symbol,
                "direction": direction,
                "strategy": strategy,
                "confidence": confidence,
                "reasoning": reasoning,
                "market_context": market_context,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_trade_record(
        cls,
        trade: Dict[str, Any],
        memory_ctx: Optional[MemoryContext] = None,
    ) -> "TradingDecisionRecord":
        """Build a TDR from an existing trade_records row + optional memory context.

        This is the main factory method used by the /audit/ endpoints.
        """
        market_context = trade.get("market_context") or {}
        if isinstance(market_context, str):
            market_context = json.loads(market_context)

        event_log = market_context.get("event_log", {})
        regime_data = market_context.get("regime", {})

        market = MarketSnapshot(
            price=market_context.get("price"),
            session=market_context.get("session"),
            regime=regime_data.get("regime"),
            atr_m5=event_log.get("atr_m5"),
            atr_h1=regime_data.get("atr_h1"),
            atr_d1=regime_data.get("atr_d1"),
            spread_points=event_log.get("spread_points"),
            ema_fast_h1=event_log.get("ema_fast_h1"),
            ema_slow_h1=event_log.get("ema_slow_h1"),
        )

        # Compute data_hash from original inputs
        data_hash = cls.compute_hash(
            trade_id=trade.get("id", ""),
            timestamp=trade.get("timestamp", ""),
            symbol=trade.get("symbol", ""),
            direction=trade.get("direction", ""),
            strategy=trade.get("strategy", ""),
            confidence=trade.get("confidence", 0.0),
            reasoning=trade.get("reasoning", ""),
            market_context=market_context,
        )

        # Parse references into memory context
        refs = trade.get("references", [])
        if isinstance(refs, str):
            refs = json.loads(refs)

        mem = memory_ctx or MemoryContext(similar_trades=refs)
        if not memory_ctx and refs:
            mem.similar_trades = refs
            mem.recall_count = len(refs)

        return cls(
            record_id=trade.get("id", ""),
            timestamp=trade.get("timestamp", datetime.min),
            decision_type="ENTRY",
            symbol=trade.get("symbol", ""),
            direction=trade.get("direction"),
            strategy=trade.get("strategy", ""),
            signal_source=trade.get("reasoning", ""),
            confidence_score=trade.get("confidence", 0.0),
            market=market,
            memory=mem,
            risk=RiskSnapshot(
                position_size=trade.get("lot_size"),
            ),
            exit_timestamp=trade.get("exit_timestamp"),
            exit_reason=trade.get("exit_reasoning"),
            pnl=trade.get("pnl"),
            pnl_r=trade.get("pnl_r"),
            hold_duration_minutes=trade.get("hold_duration"),
            data_hash=data_hash,
        )

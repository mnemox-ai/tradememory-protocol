"""Trading agents for A/B simulation experiments.

BaseAgent: Mechanical execution — no learning, no calibration.
CalibratedAgent: Same strategy + TradeMemory calibration layer (DQS + changepoint + Kelly).
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tradememory.data.context_builder import MarketContext
from tradememory.evolution.backtester import check_entry, evaluate_condition
from tradememory.evolution.models import CandidatePattern

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    """Entry signal from an agent."""

    direction: str  # "long" or "short"
    lot_size: float
    reason: str


@dataclass
class SimulatedTrade:
    """Completed trade with full metadata."""

    trade_id: str
    entry_bar_index: int
    exit_bar_index: int
    entry_price: float
    exit_price: float
    direction: str
    lot_size: float
    pnl: float
    pnl_r: float  # PnL in R-multiples (pnl / risk_per_trade)
    hold_bars: int
    exit_reason: str = ""
    dqs_score: Optional[float] = None
    dqs_tier: Optional[str] = None
    changepoint_prob: Optional[float] = None
    cusum_alert: Optional[bool] = None


class BaseAgent:
    """Agent A — mechanical execution, no learning, no calibration."""

    def __init__(self, strategy: CandidatePattern, fixed_lot: float = 0.01):
        self.strategy = strategy
        self.fixed_lot = fixed_lot
        self.trades: List[SimulatedTrade] = []

    @property
    def name(self) -> str:
        return f"BaseAgent({self.strategy.name})"

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        """Evaluate entry conditions. Returns TradeSignal or None."""
        if check_entry(self.strategy, context):
            return TradeSignal(
                direction=self.strategy.entry_condition.direction,
                lot_size=self.fixed_lot,
                reason=f"Entry conditions met for {self.strategy.name}",
            )
        return None

    def on_trade_complete(self, trade: SimulatedTrade):
        """BaseAgent only records, no calibration."""
        self.trades.append(trade)


class CalibratedAgent(BaseAgent):
    """Agent B — same strategy + TradeMemory calibration layer.

    Calibration gates (applied in order):
    1. DQS check — skip tier → reject trade
    2. DQS tier multiplier — go=1.0, proceed=0.7, caution=0.3
    3. Changepoint — if cp_prob > 0.5 or CUSUM alert → lot × 0.5
    4. Kelly sizing — use procedural memory's kelly_fraction if available
    """

    def __init__(
        self,
        strategy: CandidatePattern,
        db_path: Optional[str] = None,
        fixed_lot: float = 0.01,
        hazard_lambda: float = 50.0,
    ):
        super().__init__(strategy, fixed_lot)
        from tradememory.db import Database
        from tradememory.owm.changepoint import BayesianChangepoint
        from tradememory.owm.dqs import DQSEngine

        if db_path is None:
            import tempfile
            db_path = os.path.join(tempfile.mkdtemp(), f"sim_{uuid.uuid4().hex[:8]}.db")
        self._db_path = db_path
        self.db = Database(db_path=db_path)
        self.changepoint = BayesianChangepoint(hazard_lambda=hazard_lambda)
        self.dqs_engine = DQSEngine(self.db)
        self._trade_count = 0
        self._last_cp_prob = 0.0
        self._last_cusum_alert = False
        self._last_dqs_score: Optional[float] = None
        self._last_dqs_tier: Optional[str] = None

        # DQS log and changepoint log for reporting
        self.dqs_log: List[Dict[str, Any]] = []
        self.changepoint_log: List[Dict[str, Any]] = []
        self.skipped_signals: int = 0

    @property
    def name(self) -> str:
        return f"CalibratedAgent({self.strategy.name})"

    def should_trade(self, context: MarketContext) -> Optional[TradeSignal]:
        """BaseAgent entry logic + calibration gates."""
        base_signal = super().should_trade(context)
        if base_signal is None:
            return None

        # 1. Compute DQS
        try:
            dqs = self.dqs_engine.compute(
                symbol=context.symbol or "UNKNOWN",
                strategy_name=self.strategy.name,
                direction=base_signal.direction,
                proposed_lot_size=base_signal.lot_size,
                context_regime=context.regime.value if context.regime else None,
                context_atr_d1=context.atr_d1,
            )
            self._last_dqs_score = dqs.score
            self._last_dqs_tier = dqs.tier

            self.dqs_log.append({
                "trade_index": self._trade_count,
                "score": dqs.score,
                "tier": dqs.tier,
                "multiplier": dqs.position_multiplier,
                "factors": {k: v["score"] for k, v in dqs.factors.items()},
            })

            if dqs.tier == "skip":
                self.skipped_signals += 1
                return None

            # 2. Apply DQS tier multiplier
            lot = base_signal.lot_size * dqs.position_multiplier
        except Exception as e:
            logger.warning("DQS computation failed: %s — proceeding without gate", e)
            lot = base_signal.lot_size
            self._last_dqs_score = None
            self._last_dqs_tier = None

        # 3. Changepoint discount
        if self._last_cp_prob > 0.5 or self._last_cusum_alert:
            lot *= 0.5

        # 4. Kelly sizing from procedural memory
        try:
            procs = self.db.query_procedural(
                strategy=self.strategy.name,
                symbol=context.symbol or "UNKNOWN",
                limit=1,
            )
            if procs:
                kelly = procs[0].get("kelly_fraction_suggested")
                if kelly and kelly > 0:
                    lot = min(lot, kelly)
        except Exception:
            pass  # No procedural memory yet — use DQS-adjusted lot

        if lot <= 0:
            self.skipped_signals += 1
            return None

        return TradeSignal(
            direction=base_signal.direction,
            lot_size=lot,
            reason=f"Calibrated: DQS={self._last_dqs_score}, tier={self._last_dqs_tier}",
        )

    def on_trade_complete(self, trade: SimulatedTrade):
        """Record to TradeMemory + update changepoint."""
        super().on_trade_complete(trade)
        self._trade_count += 1

        # Attach DQS info to trade
        trade.dqs_score = self._last_dqs_score
        trade.dqs_tier = self._last_dqs_tier

        symbol = "UNKNOWN"
        # Try to get symbol from context
        if hasattr(self, '_current_symbol'):
            symbol = self._current_symbol

        # Write to episodic memory
        try:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).isoformat()
            self.db.insert_episodic({
                "id": trade.trade_id,
                "timestamp": ts,
                "context_json": {"symbol": symbol, "dqs_score": trade.dqs_score},
                "context_regime": None,
                "context_volatility_regime": None,
                "context_session": None,
                "context_atr_d1": None,
                "context_atr_h1": None,
                "strategy": self.strategy.name,
                "direction": trade.direction,
                "entry_price": trade.entry_price,
                "lot_size": trade.lot_size,
                "exit_price": trade.exit_price,
                "pnl": trade.pnl,
                "pnl_r": trade.pnl_r,
                "hold_duration_seconds": trade.hold_bars * 3600,  # assume 1H bars
                "max_adverse_excursion": None,
                "reflection": None,
                "confidence": 0.5,
                "tags": [],
                "retrieval_strength": 1.0,
                "retrieval_count": 0,
                "last_retrieved": None,
            })
        except Exception as e:
            logger.warning("Failed to store episodic memory: %s", e)

        # Update procedural memory
        try:
            from tradememory.owm_helpers import update_procedural_from_trade
            update_procedural_from_trade(
                self.db,
                symbol=symbol,
                strategy_name=self.strategy.name,
                pnl=trade.pnl,
                lot_size=trade.lot_size,
                hold_duration_seconds=trade.hold_bars * 3600,
                pnl_r=trade.pnl_r,
            )
        except Exception as e:
            logger.warning("Failed to update procedural memory: %s", e)

        # Update affective state
        try:
            from tradememory.owm_helpers import update_affective_from_trade
            update_affective_from_trade(
                self.db,
                pnl=trade.pnl,
                confidence=0.5,
                strategy_name=self.strategy.name,
                symbol=symbol,
            )
        except Exception as e:
            logger.warning("Failed to update affective state: %s", e)

        # Update changepoint detector
        try:
            result = self.changepoint.update({
                "won": trade.pnl > 0,
                "pnl_r": trade.pnl_r,
                "hold_seconds": trade.hold_bars * 3600,
            })
            self._last_cp_prob = result.changepoint_probability
            self._last_cusum_alert = result.cusum_alert
            trade.changepoint_prob = result.changepoint_probability
            trade.cusum_alert = result.cusum_alert

            self.changepoint_log.append({
                "trade_index": self._trade_count,
                "cp_prob": result.changepoint_probability,
                "cusum_alert": result.cusum_alert,
                "cusum_value": result.cusum_value,
                "max_run_length": result.max_run_length,
            })
        except Exception as e:
            logger.warning("Changepoint update failed: %s", e)

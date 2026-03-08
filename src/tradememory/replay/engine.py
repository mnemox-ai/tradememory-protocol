"""ReplayEngine — orchestrates the full LLM trading agent replay loop.

Load CSV → sliding_window → compute indicators → build prompt → call LLM
→ execute decision → track position → store to OWM memory → log to JSONL.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.tradememory.replay.data_loader import parse_mt5_csv, sliding_window
from src.tradememory.replay.indicators import compute_all_indicators
from src.tradememory.replay.llm_client import LLMClient
from src.tradememory.replay.models import (
    AgentDecision,
    Bar,
    DecisionType,
    IndicatorSnapshot,
    Position,
    PositionState,
    ReplayConfig,
)
from src.tradememory.replay.position_tracker import PositionTracker
from src.tradememory.replay.prompt import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Orchestrates: CSV → sliding_window → indicators → LLM → position → OWM → JSONL."""

    def __init__(self, config: ReplayConfig):
        self.config = config
        self.tracker = PositionTracker(
            lot_size=config.lot_size,
            initial_equity=config.initial_equity,
        )
        self.decisions: List[Dict[str, Any]] = []
        self.total_bars = 0
        self._checkpoint_path = Path(config.data_path).with_suffix(".checkpoint.json")

    def run(self, dry_run: bool = False) -> Dict[str, Any]:
        """Main replay loop.

        Args:
            dry_run: If True, parse CSV + compute indicators only (no LLM calls).

        Returns:
            Summary dict from _build_summary().
        """
        bars = parse_mt5_csv(self.config.data_path)
        self.total_bars = len(bars)

        if not bars:
            return self._build_summary()

        # Initialize LLM client only if not dry run
        llm: Optional[LLMClient] = None
        if not dry_run:
            llm = LLMClient(self.config)

        # Initialize DB for memory storage
        db = None
        if self.config.store_to_memory and not dry_run:
            from src.tradememory.db import Database

            db = Database(self.config.db_path)

        system_prompt = build_system_prompt()
        last_decision_idx: Optional[int] = None
        decision_count = 0

        for bar_idx, window, current_bar in sliding_window(
            bars, self.config.window_size, self.config.decision_interval
        ):
            # Skip bars before resume point
            if bar_idx < self.config.resume_from_bar:
                continue

            # Cost control: stop after max_decisions
            if self.config.max_decisions > 0 and decision_count >= self.config.max_decisions:
                break

            # Check intermediate bars for SL/TP between decision points
            if last_decision_idx is not None:
                closed = self._check_intermediate_bars(bars, last_decision_idx, bar_idx)
                if closed and db:
                    self._store_to_memory(db, closed, window)

            last_decision_idx = bar_idx

            # Compute indicators
            indicators = compute_all_indicators(window)

            if dry_run:
                self.decisions.append(
                    {
                        "bar_idx": bar_idx,
                        "timestamp": current_bar.timestamp.isoformat(),
                        "close": current_bar.close,
                        "indicators": indicators.model_dump(),
                        "decision": "DRY_RUN",
                    }
                )
                continue

            # Build prompt
            recent_trades = [
                {
                    "strategy": p.strategy,
                    "result": p.state.value,
                    "pnl": p.pnl or 0.0,
                }
                for p in self.tracker.closed_positions[-5:]
            ]

            user_prompt = build_user_prompt(
                current_bar=current_bar,
                window_bars=window,
                indicators=indicators,
                open_position=self.tracker.current_position,
                recent_trades=recent_trades or None,
                equity=self.tracker.equity,
            )

            # Call LLM
            assert llm is not None
            decision = llm.decide(system_prompt, user_prompt)

            # Execute decision
            self._execute_decision(decision, current_bar)

            # Log entry
            entry = {
                "bar_idx": bar_idx,
                "timestamp": current_bar.timestamp.isoformat(),
                "close": current_bar.close,
                "decision": decision.decision.value,
                "confidence": decision.confidence,
                "strategy": decision.strategy_used,
                "equity": self.tracker.equity,
                "position": (
                    self.tracker.current_position.trade_id
                    if self.tracker.current_position
                    else None
                ),
            }
            self.decisions.append(entry)
            self._log_jsonl(entry)

            # Checkpoint for resumability
            self._checkpoint(bar_idx)
            decision_count += 1

        # Check remaining intermediate bars after last decision
        if last_decision_idx is not None and last_decision_idx < len(bars) - 1:
            closed = self._check_intermediate_bars(
                bars, last_decision_idx, len(bars) - 1
            )
            if closed and db:
                self._store_to_memory(db, closed, bars[-self.config.window_size :])

        # EOD close any open position
        if self.tracker.current_position and bars:
            closed = self.tracker.close_position(bars[-1], PositionState.CLOSED_EOD)
            if db:
                self._store_to_memory(
                    db, closed, bars[-self.config.window_size :]
                )

        return self._build_summary(llm)

    def _execute_decision(self, decision: AgentDecision, bar: Bar) -> None:
        """Execute a BUY/SELL/CLOSE decision."""
        if decision.decision in (DecisionType.BUY, DecisionType.SELL):
            if self.tracker.current_position is None:
                self.tracker.open_position(decision, bar)
        elif decision.decision == DecisionType.CLOSE:
            if self.tracker.current_position is not None:
                self.tracker.close_position(bar, PositionState.CLOSED_AGENT)

    def _check_intermediate_bars(
        self, bars: List[Bar], from_idx: int, to_idx: int
    ) -> Optional[Position]:
        """Check bars between decision points for SL/TP hits."""
        for i in range(from_idx + 1, to_idx + 1):
            closed = self.tracker.check_bar(bars[i])
            if closed:
                return closed
        return None

    def _store_to_memory(
        self, db: Any, position: Position, context_bars: List[Bar]
    ) -> None:
        """Store a closed position to OWM episodic memory."""
        session = self._classify_session(position.entry_time)
        regime = self._classify_regime(position)

        hold_seconds = 0
        if position.exit_time and position.entry_time:
            hold_seconds = int(
                (position.exit_time - position.entry_time).total_seconds()
            )

        # Compute ATR from context bars if available
        atr_d1 = 0.0
        atr_h1 = 0.0
        if context_bars:
            ind = compute_all_indicators(context_bars)
            atr_d1 = ind.atr_d1 or 0.0
            atr_h1 = ind.atr_h1 or 0.0

        data = {
            "id": f"replay_{position.trade_id}",
            "timestamp": position.entry_time.isoformat(),
            "context_json": json.dumps({
                "source": "replay_engine",
                "data_file": self.config.data_path,
            }),
            "context_regime": regime,
            "context_volatility_regime": "unknown",
            "context_session": session,
            "context_atr_d1": atr_d1,
            "context_atr_h1": atr_h1,
            "strategy": position.strategy,
            "direction": position.direction,
            "entry_price": position.entry_price,
            "lot_size": self.config.lot_size,
            "exit_price": position.exit_price or 0.0,
            "pnl": position.pnl or 0.0,
            "pnl_r": position.pnl_r or 0.0,
            "hold_duration_seconds": hold_seconds,
            "max_adverse_excursion": position.max_adverse_excursion,
            "reflection": position.reasoning,
            "confidence": position.confidence,
            "tags": json.dumps(["replay", position.strategy, position.state.value]),
            "retrieval_strength": 1.0,
            "retrieval_count": 0,
            "last_retrieved": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.insert_episodic(data)

    @staticmethod
    def _classify_session(timestamp: datetime) -> str:
        """Classify trading session from server time (GMT+2)."""
        hour = timestamp.hour
        if 0 <= hour < 7:
            return "asian"
        elif 7 <= hour < 14:
            return "london"
        elif 14 <= hour < 21:
            return "new_york"
        return "off_hours"

    @staticmethod
    def _classify_regime(position: Position) -> str:
        """Simple regime classification based on trade outcome."""
        if position.pnl is None:
            return "unknown"
        if position.state == PositionState.CLOSED_TP:
            return "trending"
        elif position.state == PositionState.CLOSED_SL:
            return "range_bound"
        return "unknown"

    def _log_jsonl(self, entry: Dict[str, Any]) -> None:
        """Append a log entry to the JSONL file."""
        if not self.config.log_path:
            return
        with open(self.config.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _checkpoint(self, bar_idx: int) -> None:
        """Save checkpoint for resumability."""
        data = {
            "bar_idx": bar_idx,
            "equity": self.tracker.equity,
            "trades": len(self.tracker.closed_positions),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._checkpoint_path.write_text(json.dumps(data))

    def _build_summary(self, llm: Optional[LLMClient] = None) -> Dict[str, Any]:
        """Build summary dict with trading performance metrics."""
        closed = self.tracker.closed_positions
        wins = [p for p in closed if (p.pnl or 0) > 0]
        losses = [p for p in closed if (p.pnl or 0) < 0]

        gross_profit = sum(p.pnl for p in wins if p.pnl)
        gross_loss = abs(sum(p.pnl for p in losses if p.pnl))

        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        return {
            "total_bars": self.total_bars,
            "decisions": len(self.decisions),
            "trades": len(closed),
            "equity": self.tracker.equity,
            "win_rate": len(wins) / len(closed) if closed else 0.0,
            "profit_factor": profit_factor,
            "tokens": llm.total_tokens_used if llm else 0,
            "cost": llm.total_cost_usd if llm else 0.0,
        }


def run_replay(config: ReplayConfig, dry_run: bool = False) -> Dict[str, Any]:
    """Convenience function to run a full replay."""
    engine = ReplayEngine(config)
    return engine.run(dry_run=dry_run)

"""Store one finished trade in every memory layer.

Shared by the `remember_trade` MCP tool and by the importers in
`tradememory.sync`, so a trade that arrives from a broker's fill history is
remembered exactly the way an agent-reported trade is.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .db import Database
from .embedding import embed_trade_context
from .owm_helpers import (
    update_affective_from_trade,
    update_procedural_from_trade,
    update_semantic_from_trade,
)

logger = logging.getLogger(__name__)


def hold_seconds_between(entry_timestamp: Optional[str], exit_timestamp: Optional[str]) -> Optional[int]:
    """Seconds between two ISO timestamps, or None when either is missing, unparseable or reversed."""
    if not (entry_timestamp and exit_timestamp):
        return None
    try:
        seconds = int((datetime.fromisoformat(exit_timestamp) - datetime.fromisoformat(entry_timestamp)).total_seconds())
    except (ValueError, TypeError):
        return None
    return seconds if seconds >= 0 else None


def insert_trade_record(
    db: Database,
    *,
    trade_id: str,
    timestamp: str,
    symbol: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    pnl: float,
    pnl_r: Optional[float],
    strategy_name: str,
    market_context: str,
    confidence: float = 0.5,
    reflection: Optional[str] = None,
    lot_size: Optional[float] = None,
    tags: Optional[list] = None,
) -> None:
    """The trade_records row for a finished trade (the table the audit trail is built on)."""
    db.insert_trade({
        "id": trade_id,
        "timestamp": timestamp,
        "symbol": symbol,
        "direction": direction,
        "lot_size": lot_size if lot_size is not None else 0.0,
        "strategy": strategy_name,
        "confidence": confidence,
        "reasoning": market_context,
        "market_context": {"description": market_context, "entry_price": entry_price},
        "references": [],
        "exit_timestamp": None,
        "exit_price": exit_price,
        "pnl": pnl,
        "pnl_r": pnl_r,
        "hold_duration": None,
        "exit_reasoning": reflection,
        "slippage": None,
        "execution_quality": None,
        "lessons": reflection,
        "tags": list(tags or []),
        "grade": None,
    })


def store_trade_memory(
    db: Database,
    *,
    trade_id: str,
    timestamp: str,
    symbol: str,
    direction: str,
    entry_price: float,
    exit_price: float,
    pnl: float,
    strategy_name: str,
    market_context: str,
    pnl_r: Optional[float] = None,
    context_regime: Optional[str] = None,
    context_atr_d1: Optional[float] = None,
    confidence: float = 0.5,
    reflection: Optional[str] = None,
    max_adverse_excursion: Optional[float] = None,
    hold_seconds: Optional[int] = None,
    lot_size: Optional[float] = None,
    extra_context: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
    compute_dqs: bool = True,
    embed: bool = True,
    trade_record: bool = True,
) -> None:
    """Write episodic memory, update semantic/procedural/affective, and (optionally) trade_records.

    ``symbol`` must already be upper-case and ``direction`` "long" or "short";
    callers validate their own input. ``trade_record=False`` is for a trade
    whose trade_records row already exists (the broker brake opens one when it
    forwards an order) and only needs its outcome filled in.
    """
    context_dict: Dict[str, Any] = {
        "symbol": symbol,
        "price": entry_price,
        "regime": context_regime,
        "atr_d1": context_atr_d1,
        "description": market_context,
    }
    if extra_context:
        context_dict.update(extra_context)

    if compute_dqs:
        # Best-effort: a DQS failure must not block storing the trade.
        try:
            from .owm.dqs import DQSEngine
            dqs_result = DQSEngine(db).compute(
                symbol=symbol,
                strategy_name=strategy_name,
                direction=direction,
                market_context=market_context,
                context_regime=context_regime,
                context_atr_d1=context_atr_d1,
            )
            context_dict["dqs_score"] = dqs_result.score
            context_dict["dqs_tier"] = dqs_result.tier
        except Exception as e:
            logger.warning(f"DQS computation skipped for trade {trade_id}: {e}")
            context_dict["dqs_score"] = None
            context_dict["dqs_tier"] = None

    db.insert_episodic({
        "id": trade_id,
        "timestamp": timestamp,
        "context_json": context_dict,
        "context_regime": context_regime,
        "context_volatility_regime": None,
        "context_session": None,
        "context_atr_d1": context_atr_d1,
        "context_atr_h1": None,
        "strategy": strategy_name,
        "direction": direction,
        "entry_price": entry_price,
        "lot_size": lot_size,
        "exit_price": exit_price,
        "pnl": pnl,
        "pnl_r": pnl_r,
        "hold_duration_seconds": hold_seconds,
        "max_adverse_excursion": max_adverse_excursion,
        "reflection": reflection,
        "confidence": confidence,
        "tags": list(tags or []),
        "retrieval_strength": 1.0,
        "retrieval_count": 0,
        "last_retrieved": None,
    })

    update_semantic_from_trade(db, symbol, strategy_name, pnl, pnl_r, context_regime, trade_id)
    # lot_size stays out of the procedural layer: its lot_vs_kelly_ratio
    # expects lots, and an imported size is in coins or shares.
    update_procedural_from_trade(db, symbol, strategy_name, pnl, hold_duration_seconds=hold_seconds, pnl_r=pnl_r)
    update_affective_from_trade(db, pnl, confidence, strategy_name=strategy_name, symbol=symbol)

    if trade_record:
        insert_trade_record(
            db, trade_id=trade_id, timestamp=timestamp, symbol=symbol, direction=direction,
            entry_price=entry_price, exit_price=exit_price, pnl=pnl, pnl_r=pnl_r,
            strategy_name=strategy_name, market_context=market_context, confidence=confidence,
            reflection=reflection, lot_size=lot_size, tags=tags,
        )

    if embed:
        # Best-effort embedding for hybrid recall.
        try:
            embedding = embed_trade_context({
                "strategy": strategy_name,
                "direction": direction,
                "context_regime": context_regime,
                "reflection": reflection,
            })
            if embedding is not None:
                db.update_episodic_embedding(trade_id, embedding)
                logger.info(f"Embedding stored for trade {trade_id} (dim={len(embedding)})")
        except Exception as e:
            logger.warning(f"Embedding generation skipped for trade {trade_id}: {e}")

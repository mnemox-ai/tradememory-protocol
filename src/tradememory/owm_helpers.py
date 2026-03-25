"""
Shared OWM helper functions used by both server.py and mcp_server.py.

Extracted to eliminate code duplication between REST and MCP entry points.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from .db import Database


def ensure_tz(ts: Optional[str]) -> str:
    """Ensure a timestamp string is timezone-aware (UTC).

    db.py uses datetime.now(timezone.utc) which produces timezone-aware timestamps.
    OWM compute_recency needs aware timestamps for subtraction.
    """
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    if "+" not in ts and "Z" not in ts and ts.count("-") <= 2:
        return ts + "+00:00"
    return ts


def update_semantic_from_trade(
    db: Database,
    symbol: str,
    strategy_name: str,
    pnl: float,
    pnl_r: Optional[float],
    context_regime: Optional[str],
    trade_id: str,
) -> None:
    """Update semantic memories with Bayesian evidence from a new trade.

    Finds existing semantic memories for the same strategy+symbol.
    If none exist, creates one. Then applies Bayesian update:
    pnl > 0 -> alpha += weight, pnl <= 0 -> beta += weight.
    weight = min(2, abs(pnl_r)) if pnl_r available, else 1.0.
    """
    existing = db.query_semantic(strategy=strategy_name, symbol=symbol, limit=10)

    weight = min(2.0, abs(pnl_r)) if pnl_r is not None else 1.0
    confirmed = pnl > 0

    if existing:
        for mem in existing:
            db.update_semantic_bayesian(
                memory_id=mem["id"],
                confirmed=confirmed,
                weight=weight,
                evidence_id=trade_id,
            )
    else:
        sem_id = f"sem-{strategy_name.lower()}-{symbol.lower()}-{uuid.uuid4().hex[:8]}"
        alpha = 1.0 + (weight if confirmed else 0.0)
        beta = 1.0 + (0.0 if confirmed else weight)
        db.insert_semantic({
            "id": sem_id,
            "proposition": f"{strategy_name} on {symbol} tends to be profitable",
            "alpha": alpha,
            "beta": beta,
            "sample_size": 1,
            "strategy": strategy_name,
            "symbol": symbol,
            "regime": context_regime,
            "volatility_regime": None,
            "validity_conditions": {"symbol": symbol, "strategy": strategy_name},
            "last_confirmed": trade_id if confirmed else None,
            "last_contradicted": None if confirmed else trade_id,
            "source": "remember_trade",
            "retrieval_strength": 1.0,
        })


def update_procedural_from_trade(
    db: Database,
    symbol: str,
    strategy_name: str,
    pnl: float,
    lot_size: float = 0.0,
) -> None:
    """Update procedural memory with running averages from a new trade."""
    proc_id = f"proc-{strategy_name.lower()}-{symbol.lower()}"
    existing = db.query_procedural(strategy=strategy_name, symbol=symbol, limit=1)

    if existing:
        rec = existing[0]
        n = rec.get("sample_size", 0)
        new_n = n + 1

        old_mean = rec.get("actual_lot_mean") or 0.0
        new_mean = old_mean + (lot_size - old_mean) / new_n if new_n > 0 else lot_size

        db.upsert_procedural({
            "id": proc_id,
            "strategy": strategy_name,
            "symbol": symbol,
            "behavior_type": "trade_execution",
            "sample_size": new_n,
            "avg_hold_winners": rec.get("avg_hold_winners") or 0.0,
            "avg_hold_losers": rec.get("avg_hold_losers") or 0.0,
            "disposition_ratio": rec.get("disposition_ratio"),
            "actual_lot_mean": new_mean,
            "actual_lot_variance": rec.get("actual_lot_variance") or 0.0,
            "kelly_fraction_suggested": rec.get("kelly_fraction_suggested"),
            "lot_vs_kelly_ratio": rec.get("lot_vs_kelly_ratio"),
        })
    else:
        db.upsert_procedural({
            "id": proc_id,
            "strategy": strategy_name,
            "symbol": symbol,
            "behavior_type": "trade_execution",
            "sample_size": 1,
            "avg_hold_winners": 0.0,
            "avg_hold_losers": 0.0,
            "disposition_ratio": None,
            "actual_lot_mean": lot_size,
            "actual_lot_variance": 0.0,
            "kelly_fraction_suggested": None,
            "lot_vs_kelly_ratio": None,
        })


def update_affective_from_trade(
    db: Database,
    pnl: float,
    confidence: float,
) -> None:
    """Update affective state: EWMA confidence, streaks, equity/drawdown."""
    state = db.load_affective()

    ewma_alpha = 0.3

    if state is None:
        db.init_affective(peak_equity=10000.0, current_equity=10000.0)
        state = db.load_affective()
        if state is None:
            return

    old_conf = state.get("confidence_level", 0.5)
    new_conf = ewma_alpha * confidence + (1 - ewma_alpha) * old_conf
    new_conf = max(0.0, min(1.0, new_conf))

    if pnl > 0:
        consec_wins = state.get("consecutive_wins", 0) + 1
        consec_losses = 0
    else:
        consec_wins = 0
        consec_losses = state.get("consecutive_losses", 0) + 1

    current_equity = state.get("current_equity", 10000.0) + pnl
    peak_equity = max(state.get("peak_equity", current_equity), current_equity)
    drawdown_state = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0.0

    db.save_affective({
        "confidence_level": new_conf,
        "risk_appetite": state.get("risk_appetite", 1.0),
        "momentum_bias": state.get("momentum_bias", 0.0),
        "peak_equity": peak_equity,
        "current_equity": current_equity,
        "drawdown_state": drawdown_state,
        "max_acceptable_drawdown": state.get("max_acceptable_drawdown", 0.20),
        "consecutive_wins": consec_wins,
        "consecutive_losses": consec_losses,
        "history_json": state.get("history_json", []),
    })

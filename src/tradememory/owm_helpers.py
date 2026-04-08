"""
Shared OWM helper functions used by both server.py and mcp_server.py.

Extracted to eliminate code duplication between REST and MCP entry points.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .db import Database
from .owm.changepoint import BayesianChangepoint

logger = logging.getLogger(__name__)

DRIFT_THRESHOLD = 0.15  # 15% divergence triggers drift flag
CHANGEPOINT_THRESHOLD = 0.8  # Bayesian changepoint detection threshold


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


def _check_episodic_drift(
    db: Database,
    strategy_name: str,
    symbol: str,
    bayesian_confidence: float,
) -> dict:
    """Check if recent episodic outcomes drift from Bayesian belief.

    Queries last 20 episodic memories for the same strategy+symbol,
    computes recent win rate, and flags if it diverges >15% from
    the Bayesian posterior belief.

    Returns:
        Dict with drift_flag, recent_win_rate, bayesian_confidence, delta.
    """
    recent = db.query_episodic(strategy=strategy_name, limit=20)
    # Filter to same symbol
    relevant = [
        ep for ep in recent
        if (ep.get("context_json") or {}).get("symbol") == symbol
    ]

    if len(relevant) < 5:
        return {"drift_flag": False, "reason": "insufficient_data", "sample_size": len(relevant)}

    wins = sum(1 for ep in relevant if (ep.get("pnl") or 0) > 0)
    recent_wr = wins / len(relevant)
    delta = abs(recent_wr - bayesian_confidence)

    return {
        "drift_flag": delta > DRIFT_THRESHOLD,
        "recent_win_rate": round(recent_wr, 3),
        "bayesian_confidence": round(bayesian_confidence, 3),
        "delta": round(delta, 3),
        "sample_size": len(relevant),
    }


def _run_changepoint_detection(
    db: Database,
    strategy_name: str,
    symbol: str,
    pnl: float,
    pnl_r: Optional[float],
    won: bool,
) -> Optional[dict]:
    """Run Bayesian changepoint detection, loading/saving state from DB.

    Returns dict with drift_flag and diagnostics, or None if detection fails.
    """
    try:
        cp_id = f"cp-{strategy_name.lower()}-{symbol.lower()}"

        # Load existing state or create new detector
        saved = db.load_changepoint_state(strategy_name, symbol)
        if saved and saved.get("state_json"):
            state = json.loads(saved["state_json"])
            detector = BayesianChangepoint.from_state(state)
        else:
            detector = BayesianChangepoint(hazard_lambda=50.0)

        # Build observation
        observation = {
            "won": won,
            "pnl_r": pnl_r if pnl_r is not None else (pnl / 100.0),
        }

        # Run update
        result = detector.update(observation)

        # Determine if changepoint
        cp_at = None
        if result.changepoint_probability > CHANGEPOINT_THRESHOLD:
            cp_at = result.observation_count

        # Save state
        db.save_changepoint_state(
            cp_id=cp_id,
            strategy=strategy_name,
            symbol=symbol,
            state_json=json.dumps(detector.get_state()),
            observation_count=result.observation_count,
            changepoint_prob=result.changepoint_probability,
            changepoint_at=cp_at,
        )

        return {
            "drift_flag": result.changepoint_probability > CHANGEPOINT_THRESHOLD,
            "changepoint_probability": round(result.changepoint_probability, 4),
            "observation_count": result.observation_count,
            "max_run_length": result.max_run_length,
            "method": "bayesian_bocpd",
        }
    except Exception as e:
        logger.warning("Changepoint detection failed for %s/%s: %s", strategy_name, symbol, e)
        return None


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

    After Bayesian update, checks episodic drift: if the recent 20 trades'
    win rate diverges >15% from the Bayesian posterior, sets drift_flag
    in validity_conditions.
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

        mem = existing[0]

        # --- Bayesian Changepoint Detection ---
        cp_drift = _run_changepoint_detection(
            db, strategy_name, symbol, pnl, pnl_r, confirmed,
        )

        if cp_drift is not None and cp_drift.get("drift_flag"):
            logger.info(
                "Changepoint detected for %s/%s: cp_prob=%.3f (obs=%d)",
                strategy_name, symbol,
                cp_drift.get("changepoint_probability", 0),
                cp_drift.get("observation_count", 0),
            )
            vc = mem.get("validity_conditions") or {}
            if isinstance(vc, str):
                try:
                    vc = json.loads(vc)
                except Exception:
                    vc = {}
            vc["drift_flag"] = True
            vc["drift_info"] = cp_drift
            db.update_semantic_validity_conditions(mem["id"], vc)
        else:
            # Fallback: heuristic episodic drift check
            new_alpha = mem["alpha"] + (weight if confirmed else 0.0)
            new_beta = mem["beta"] + (0.0 if confirmed else weight)
            bayesian_conf = new_alpha / (new_alpha + new_beta) if (new_alpha + new_beta) > 0 else 0.5

            drift_info = _check_episodic_drift(db, strategy_name, symbol, bayesian_conf)
            if drift_info["drift_flag"]:
                logger.info(
                    "Heuristic drift detected for %s/%s: recent_wr=%.3f vs bayesian=%.3f (delta=%.3f)",
                    strategy_name, symbol,
                    drift_info.get("recent_win_rate", 0),
                    drift_info.get("bayesian_confidence", 0),
                    drift_info.get("delta", 0),
                )
                vc = mem.get("validity_conditions") or {}
                if isinstance(vc, str):
                    try:
                        vc = json.loads(vc)
                    except Exception:
                        vc = {}
                vc["drift_flag"] = True
                vc["drift_info"] = drift_info
                db.update_semantic_validity_conditions(mem["id"], vc)
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


def _compute_kelly_simple(win_rate: float, avg_win: float, avg_loss: float) -> Optional[float]:
    """Compute simple Kelly fraction: f* = p/a - q/b.

    Args:
        win_rate: proportion of winning trades [0, 1]
        avg_win: average winning R-multiple (positive)
        avg_loss: average losing R-multiple (positive magnitude)

    Returns:
        Kelly fraction clamped to [0, 0.5], or None if insufficient data.
    """
    if avg_win <= 0 or avg_loss <= 0 or win_rate <= 0:
        return None
    q = 1.0 - win_rate
    f_star = win_rate / avg_loss - q / avg_win
    return max(0.0, min(0.5, f_star * 0.25))  # quarter-Kelly


def update_procedural_from_trade(
    db: Database,
    symbol: str,
    strategy_name: str,
    pnl: float,
    lot_size: float = 0.0,
    hold_duration_seconds: Optional[int] = None,
    pnl_r: Optional[float] = None,
) -> None:
    """Update procedural memory with running averages from a new trade.

    Computes:
    - avg_hold_winners / avg_hold_losers (from hold_duration_seconds)
    - kelly_fraction_suggested (from episodic win/loss statistics)
    - actual_lot_mean (running average)
    - disposition_ratio (avg_hold_winners / avg_hold_losers when both > 0)
    """
    proc_id = f"proc-{strategy_name.lower()}-{symbol.lower()}"
    existing = db.query_procedural(strategy=strategy_name, symbol=symbol, limit=1)

    if existing:
        rec = existing[0]
        n = rec.get("sample_size", 0)
        new_n = n + 1

        # Running average for lot size
        old_mean = rec.get("actual_lot_mean") or 0.0
        new_mean = old_mean + (lot_size - old_mean) / new_n if new_n > 0 else lot_size

        # Update hold time averages
        avg_hw = rec.get("avg_hold_winners") or 0.0
        avg_hl = rec.get("avg_hold_losers") or 0.0

        if hold_duration_seconds is not None and hold_duration_seconds > 0:
            if pnl > 0:
                # Running average for winner hold times
                # Count wins from episodic history
                win_count = max(1, int(n * ((rec.get("disposition_ratio") or 1.0) / (1.0 + (rec.get("disposition_ratio") or 1.0)))) if n > 0 else 1)
                avg_hw = avg_hw + (hold_duration_seconds - avg_hw) / max(win_count, 1)
            else:
                loss_count = max(1, n - int(n * ((rec.get("disposition_ratio") or 1.0) / (1.0 + (rec.get("disposition_ratio") or 1.0)))) if n > 0 else 1)
                avg_hl = avg_hl + (hold_duration_seconds - avg_hl) / max(loss_count, 1)

        # Disposition ratio: avg_hold_winners / avg_hold_losers
        disp = avg_hw / avg_hl if avg_hl > 0 and avg_hw > 0 else rec.get("disposition_ratio")

        # Kelly from episodic history
        kelly = rec.get("kelly_fraction_suggested")
        episodic_trades = db.query_episodic(strategy=strategy_name, limit=50)
        ep_same_symbol = [
            ep for ep in episodic_trades
            if (ep.get("context_json") or {}).get("symbol") == symbol
        ]
        if len(ep_same_symbol) >= 10:
            wins = [ep for ep in ep_same_symbol if (ep.get("pnl_r") or ep.get("pnl") or 0) > 0]
            losses = [ep for ep in ep_same_symbol if (ep.get("pnl_r") or ep.get("pnl") or 0) <= 0]
            wr = len(wins) / len(ep_same_symbol)

            avg_win_r = sum(abs(ep.get("pnl_r") or 1.0) for ep in wins) / max(len(wins), 1)
            avg_loss_r = sum(abs(ep.get("pnl_r") or 1.0) for ep in losses) / max(len(losses), 1)

            kelly = _compute_kelly_simple(wr, avg_win_r, avg_loss_r)

        db.upsert_procedural({
            "id": proc_id,
            "strategy": strategy_name,
            "symbol": symbol,
            "behavior_type": "trade_execution",
            "sample_size": new_n,
            "avg_hold_winners": avg_hw,
            "avg_hold_losers": avg_hl,
            "disposition_ratio": disp,
            "actual_lot_mean": new_mean,
            "actual_lot_variance": rec.get("actual_lot_variance") or 0.0,
            "kelly_fraction_suggested": kelly,
            "lot_vs_kelly_ratio": (new_mean / kelly) if kelly and kelly > 0 else None,
        })
    else:
        avg_hw = float(hold_duration_seconds) if hold_duration_seconds and pnl > 0 else 0.0
        avg_hl = float(hold_duration_seconds) if hold_duration_seconds and pnl <= 0 else 0.0

        db.upsert_procedural({
            "id": proc_id,
            "strategy": strategy_name,
            "symbol": symbol,
            "behavior_type": "trade_execution",
            "sample_size": 1,
            "avg_hold_winners": avg_hw,
            "avg_hold_losers": avg_hl,
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
    strategy_name: Optional[str] = None,
    symbol: Optional[str] = None,
) -> None:
    """Update affective state: EWMA confidence, streaks, equity/drawdown.

    Also reads procedural memory: if disposition_ratio > 2.0 (cutting winners
    too early), reduces risk_appetite by 0.1 — making the affective state
    behaviorally aware, not just emotional.
    """
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

    # Read procedural memory — adjust risk_appetite based on behavioral patterns
    risk_appetite = state.get("risk_appetite", 1.0)
    if strategy_name and symbol:
        proc = db.query_procedural(strategy=strategy_name, symbol=symbol, limit=1)
        if proc:
            disp = proc[0].get("disposition_ratio")
            if disp is not None and disp > 2.0:
                # Cutting winners too early relative to losers → reduce risk appetite
                risk_appetite = max(0.1, risk_appetite - 0.1)
                logger.info(
                    "Disposition ratio %.2f > 2.0 for %s/%s — reducing risk_appetite to %.2f",
                    disp, strategy_name, symbol, risk_appetite,
                )

    db.save_affective({
        "confidence_level": new_conf,
        "risk_appetite": risk_appetite,
        "momentum_bias": state.get("momentum_bias", 0.0),
        "peak_equity": peak_equity,
        "current_equity": current_equity,
        "drawdown_state": drawdown_state,
        "max_acceptable_drawdown": state.get("max_acceptable_drawdown", 0.20),
        "consecutive_wins": consec_wins,
        "consecutive_losses": consec_losses,
        "history_json": state.get("history_json", []),
    })

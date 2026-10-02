"""OWM core recall algorithm — outcome-weighted memory scoring and retrieval.

Reference: docs/OWM_FRAMEWORK.md Section 3
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .context import ContextVector, context_similarity


@dataclass
class ScoredMemory:
    """A memory with its computed OWM recall score and component breakdown."""

    memory_id: str
    memory_type: str  # 'episodic', 'semantic', 'prospective'
    score: float
    components: Dict[str, float] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Component functions
# ---------------------------------------------------------------------------

def sigmoid(x: float) -> float:
    """Numerically stable sigmoid: 1 / (1 + exp(-x)).

    Avoids overflow by branching on the sign of x.
    """
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        ex = math.exp(x)
        return ex / (1.0 + ex)


def compute_outcome_quality(
    memory: Dict[str, Any],
    sigma_r: float = 1.5,
    k: float = 2.0,
) -> float:
    """Q(m) — outcome quality score in (0, 1).

    Formula: Q = sigmoid(k * pnl_r / sigma_r)

    For non-outcome memories (no pnl_r), falls back to confidence
    (default 0.5).
    """
    pnl_r = memory.get("pnl_r")
    if pnl_r is None:
        return memory.get("confidence", 0.5)
    return sigmoid(k * pnl_r / sigma_r)


def compute_loss_salience(
    memory: Dict[str, Any],
    pnl_scale: Optional[float] = None,
    sigma_r: float = 1.5,
    k: float = 2.0,
) -> float:
    """L(m) — how strongly a memory counts as a loss, in (0, 1).

    The mirror image of Q: L = sigmoid(-k * pnl_r / sigma_r), so a -2R trade
    scores high and a +2R trade scores low. A memory without pnl_r but with
    pnl (an imported fill history has no stop, so no R) is measured in units
    of ``pnl_scale``, the typical absolute P&L of the memories being ranked.
    Memories with no outcome at all sit at the neutral 0.5.
    """
    pnl_r = memory.get("pnl_r")
    if pnl_r is not None:
        return sigmoid(-k * pnl_r / sigma_r)
    pnl = memory.get("pnl")
    if pnl is not None and pnl_scale:
        return sigmoid(-k * (pnl / pnl_scale) / sigma_r)
    return 0.5


def typical_abs_pnl(memories: List[Dict[str, Any]]) -> Optional[float]:
    """Median absolute pnl over memories that have one; None when there is none."""
    values = sorted(abs(m["pnl"]) for m in memories if m.get("pnl"))
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


RECALL_ORDERS = ("outcome", "losses_first")


def compute_recency(
    timestamp_iso: str,
    tau: float = 30.0,
    d: float = 0.5,
) -> float:
    """Rec(m) — power-law temporal decay in (0, 1].

    Formula: Rec = (1 + age_days / tau) ^ (-d)
    """
    ts = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
    return math.pow(1.0 + age_days / tau, -d)


def compute_confidence_factor(confidence: float) -> float:
    """Conf(m) — maps confidence [0, 1] to [0.5, 1.0].

    Formula: Conf = 0.5 + 0.5 * confidence
    """
    return 0.5 + 0.5 * max(0.0, min(1.0, confidence))


def compute_affective_modulation(
    memory: Dict[str, Any],
    drawdown_state: float = 0.0,
    consecutive_losses: int = 0,
    alpha: float = 0.3,
) -> float:
    """Aff(m) — affective modulation in [0.7, 1.3].

    Boosts or suppresses memories based on current emotional / risk state.
    """
    pnl_r = memory.get("pnl_r")

    relevance = 0.0
    if drawdown_state > 0.5:
        if pnl_r is not None and pnl_r < -1.5:
            relevance = 0.5   # Boost large-loss memories during drawdown
        elif pnl_r is not None and pnl_r > 2.0:
            relevance = 0.3   # Also surface big wins as reference
    elif consecutive_losses >= 3:
        if pnl_r is not None and pnl_r > 0:
            relevance = 0.3   # Surface winners during losing streak
        else:
            relevance = -0.2  # Suppress loss memories

    raw = 1.0 + alpha * relevance
    return max(0.7, min(1.3, raw))


# ---------------------------------------------------------------------------
# Main recall
# ---------------------------------------------------------------------------

def outcome_weighted_recall(
    query_context: ContextVector,
    memories: List[Dict[str, Any]],
    affective_state: Optional[Dict[str, Any]] = None,
    limit: int = 10,
    order: str = "outcome",
) -> List[ScoredMemory]:
    """Core OWM recall — score, rank, and return top memories.

    Each memory dict is expected to have:
      - id: str
      - memory_type: str ('episodic' | 'semantic' | 'prospective')
      - timestamp: ISO-8601 string
      - confidence: float [0, 1]
      - context: dict  (fields matching ContextVector)
      - pnl_r: Optional[float]  (R-multiple, episodic only)

    affective_state dict may contain:
      - drawdown_state: float [0, 1]
      - consecutive_losses: int

    order:
      - "outcome" (default): better outcomes rank higher (Q), modulated by
        the current affective state.
      - "losses_first": for a pre-trade check. Losing trades in similar
        conditions rank highest (L instead of Q), and the affective
        modulation is switched off, because it would otherwise hide losses
        during a losing streak — exactly when the check matters most.
    """
    if order not in RECALL_ORDERS:
        raise ValueError(f"order must be one of {RECALL_ORDERS}, got {order!r}")
    if not memories:
        return []

    aff = affective_state or {}
    drawdown = aff.get("drawdown_state", 0.0)
    consec = aff.get("consecutive_losses", 0)
    losses_first = order == "losses_first"
    pnl_scale = typical_abs_pnl(memories) if losses_first else None

    candidates: List[ScoredMemory] = []

    for m in memories:
        mem_type = m.get("memory_type", "episodic")

        # Recency params differ by type
        if mem_type == "semantic":
            tau, d_exp = 180.0, 0.3
        else:
            tau, d_exp = 30.0, 0.5

        ctx = m.get("context") or {}
        mem_ctx = ContextVector(**{
            k: v for k, v in ctx.items()
            if k in ContextVector.__dataclass_fields__
        })
        sim = context_similarity(mem_ctx, query_context)
        rec = compute_recency(m.get("timestamp", datetime.now(timezone.utc).isoformat()), tau=tau, d=d_exp)
        conf = compute_confidence_factor(m.get("confidence", 0.5))

        if losses_first:
            weight = compute_loss_salience(m, pnl_scale=pnl_scale)
            aff_mod = 1.0
            weight_name = "Loss"
        else:
            weight = compute_outcome_quality(m)
            aff_mod = compute_affective_modulation(m, drawdown_state=drawdown, consecutive_losses=consec)
            weight_name = "Q"

        score = weight * sim * rec * conf * aff_mod

        candidates.append(ScoredMemory(
            memory_id=m.get("id", ""),
            memory_type=mem_type,
            score=score,
            components={weight_name: weight, "Sim": sim, "Rec": rec, "Conf": conf, "Aff": aff_mod},
            data=m,
        ))

    candidates.sort(key=lambda x: x.score, reverse=True)
    return candidates[:limit]

"""OWM (Outcome-Weighted Memory) module."""

from .context import ContextVector, context_similarity
from .decay import episodic_decay, regime_match_factor, semantic_decay
from .kelly import kelly_from_memory
from .recall import (
    ScoredMemory,
    compute_affective_modulation,
    compute_confidence_factor,
    compute_outcome_quality,
    compute_recency,
    outcome_weighted_recall,
    sigmoid,
)

__all__ = [
    "ContextVector",
    "ScoredMemory",
    "episodic_decay",
    "compute_affective_modulation",
    "compute_confidence_factor",
    "compute_outcome_quality",
    "compute_recency",
    "context_similarity",
    "kelly_from_memory",
    "outcome_weighted_recall",
    "regime_match_factor",
    "semantic_decay",
    "sigmoid",
]

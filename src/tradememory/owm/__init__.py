"""OWM (Outcome-Weighted Memory) module."""

from .affective import ewma_confidence, risk_appetite
from .context import ContextVector, context_similarity
from .decay import episodic_decay, regime_match_factor, semantic_decay
from .drift import compute_context_drift, compute_drift_summary, cusum_drift_detect
from .induction import check_auto_induction
from .kelly import kelly_from_memory
from .legitimacy import compute_legitimacy_score
from .prospective import evaluate_trigger, record_outcome
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
    "check_auto_induction",
    "compute_context_drift",
    "compute_drift_summary",
    "cusum_drift_detect",
    "episodic_decay",
    "evaluate_trigger",
    "ewma_confidence",
    "compute_affective_modulation",
    "compute_confidence_factor",
    "compute_outcome_quality",
    "compute_recency",
    "context_similarity",
    "compute_legitimacy_score",
    "kelly_from_memory",
    "outcome_weighted_recall",
    "record_outcome",
    "regime_match_factor",
    "risk_appetite",
    "semantic_decay",
    "sigmoid",
]

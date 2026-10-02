"""Hybrid recall: vector similarity + OWM fusion.

Pure function — no DB writes, no side effects.
Falls back to pure OWM when embeddings are unavailable.

Reference: ARCHITECTURE_RULES.md Section 7
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from .owm.context import ContextVector
from .owm.recall import ScoredMemory, outcome_weighted_recall

logger = logging.getLogger(__name__)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors. Returns 0.0 on degenerate input."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _memories_have_embeddings(memories: List[Dict[str, Any]]) -> bool:
    """Check if at least one memory has a non-empty embedding field."""
    return any(m.get("embedding") for m in memories)


def ensure_negative_balance(
    results: List[ScoredMemory],
    all_candidates: List[ScoredMemory],
    min_negative_ratio: float = 0.2,
) -> List[ScoredMemory]:
    """Ensure negative memories (pnl_r < 0) comprise >= min_negative_ratio of results.

    If the ratio is already met, returns results unchanged.
    Otherwise, replaces lowest-scoring positive memories with the
    highest-scoring negative memories from remaining candidates.
    """
    if not results:
        return results

    target_count = max(1, math.ceil(len(results) * min_negative_ratio))

    negative_ids = {
        r.memory_id
        for r in results
        if r.data.get("pnl_r") is not None and r.data["pnl_r"] < 0
    }

    if len(negative_ids) >= target_count:
        return results

    need = target_count - len(negative_ids)

    result_ids = {r.memory_id for r in results}
    spare_negatives = [
        c
        for c in all_candidates
        if c.memory_id not in result_ids
        and c.data.get("pnl_r") is not None
        and c.data["pnl_r"] < 0
    ]
    spare_negatives.sort(key=lambda x: x.score, reverse=True)

    if not spare_negatives:
        return results

    positives_in_result = [
        r
        for r in results
        if r.data.get("pnl_r") is None or r.data["pnl_r"] >= 0
    ]
    positives_in_result.sort(key=lambda x: x.score)

    swapped = 0
    result_list = list(results)
    for neg in spare_negatives:
        if swapped >= need:
            break
        if not positives_in_result:
            break
        victim = positives_in_result.pop(0)
        idx = next(
            (i for i, r in enumerate(result_list) if r.memory_id == victim.memory_id),
            None,
        )
        if idx is not None:
            result_list[idx] = neg
            swapped += 1

    result_list.sort(key=lambda x: x.score, reverse=True)
    return result_list


def hybrid_recall(
    query_context: ContextVector,
    query_embedding: Optional[List[float]],
    memories: List[Dict[str, Any]],
    affective_state: Optional[Dict[str, Any]] = None,
    alpha: float = 0.3,
    limit: int = 10,
    order: str = "outcome",
) -> List[ScoredMemory]:
    """Hybrid recall combining vector similarity and OWM scoring.

    Pure function — no DB writes, no side effects.

    Args:
        query_context: Current market context for OWM similarity.
        query_embedding: Query embedding vector, or None to skip vector search.
        memories: List of memory dicts (must have 'id', 'context', etc.).
        affective_state: Optional dict with 'drawdown_state', 'consecutive_losses'.
        alpha: Blend weight. 0.0 = pure OWM, 1.0 = pure vector.
        limit: Max results to return.
        order: "outcome" (default) or "losses_first"; see outcome_weighted_recall.

    Returns:
        Ranked list of ScoredMemory. In "outcome" order at least 20% of the
        results are losses; "losses_first" already puts them on top.
    """
    if not memories:
        return []

    use_vector = (
        query_embedding is not None and _memories_have_embeddings(memories)
    )
    balance = (lambda top, pool: top) if order == "losses_first" else ensure_negative_balance

    # Step 1: OWM scoring (always runs)
    owm_results = outcome_weighted_recall(
        query_context, memories, affective_state=affective_state, limit=len(memories), order=order
    )

    if not use_vector:
        # Pure OWM fallback
        top = owm_results[:limit]
        return balance(top, owm_results)

    # Step 2: Vector similarity scoring
    all_candidates: List[ScoredMemory] = []

    for owm_mem in owm_results:
        mem_embedding = owm_mem.data.get("embedding")
        if mem_embedding:
            vector_sim = _cosine_similarity(query_embedding, mem_embedding)
        else:
            vector_sim = 0.0

        owm_score = owm_mem.score
        final_score = alpha * vector_sim + (1 - alpha) * owm_score

        all_candidates.append(
            ScoredMemory(
                memory_id=owm_mem.memory_id,
                memory_type=owm_mem.memory_type,
                score=final_score,
                components={
                    **owm_mem.components,
                    "vector_sim": vector_sim,
                    "owm_score": owm_score,
                    "alpha": alpha,
                },
                data=owm_mem.data,
            )
        )

    all_candidates.sort(key=lambda x: x.score, reverse=True)
    top = all_candidates[:limit]
    return balance(top, all_candidates)

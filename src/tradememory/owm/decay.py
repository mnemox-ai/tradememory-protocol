"""Memory decay functions for episodic and semantic memories.

Implements power-law forgetting with rehearsal boost (episodic)
and slower decay with regime matching (semantic).
"""

import math
from typing import Optional


def episodic_decay(
    age_days: float,
    tau: float = 30.0,
    d: float = 0.5,
    rehearsal_count: int = 0,
) -> float:
    """Compute episodic memory strength using power-law decay with rehearsal boost.

    Formula: S(t) = (1 + t/tau)^(-d) * (1 + 0.3*ln(1+n))

    Args:
        age_days: Age of memory in days (must be >= 0).
        tau: Time constant in days (default 30).
        d: Decay exponent (default 0.5).
        rehearsal_count: Number of times the memory was rehearsed/accessed.

    Returns:
        Memory strength in (0, 1+] range. 1.0 at t=0 with no rehearsal.
    """
    if age_days < 0:
        raise ValueError("age_days must be non-negative")
    if tau <= 0:
        raise ValueError("tau must be positive")
    if d < 0:
        raise ValueError("d must be non-negative")
    if rehearsal_count < 0:
        raise ValueError("rehearsal_count must be non-negative")

    forgetting = (1 + age_days / tau) ** (-d)
    rehearsal_boost = 1 + 0.3 * math.log(1 + rehearsal_count)
    return forgetting * rehearsal_boost


def semantic_decay(
    age_days: float,
    tau: float = 180.0,
    d: float = 0.3,
) -> float:
    """Compute semantic memory strength using power-law decay.

    Semantic memories decay slower than episodic (larger tau, smaller d).

    Args:
        age_days: Age of memory in days (must be >= 0).
        tau: Time constant in days (default 180).
        d: Decay exponent (default 0.3).

    Returns:
        Memory strength in (0, 1] range. 1.0 at t=0.
    """
    if age_days < 0:
        raise ValueError("age_days must be non-negative")
    if tau <= 0:
        raise ValueError("tau must be positive")
    if d < 0:
        raise ValueError("d must be non-negative")

    return (1 + age_days / tau) ** (-d)


def regime_match_factor(
    memory_regime: Optional[str],
    current_regime: Optional[str],
) -> float:
    """Compute regime match factor for memory relevance weighting.

    Args:
        memory_regime: Regime label when memory was formed (e.g. "trending", "ranging").
        current_regime: Current market regime label.

    Returns:
        1.0 if regimes match, 0.3 if mismatch, 0.6 if either is None.
    """
    if memory_regime is None or current_regime is None:
        return 0.6
    if memory_regime == current_regime:
        return 1.0
    return 0.3

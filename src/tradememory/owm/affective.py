"""Affective state modelling: EWMA confidence and risk appetite.

EWMA confidence tracks emotional momentum from recent trade outcomes.
Risk appetite scales position sizing based on drawdown severity.
"""

import math


def ewma_confidence(outcomes: list[float], lam: float = 0.9) -> float:
    """Compute exponentially weighted moving average of trade outcomes as confidence.

    Maps raw EWMA to [0, 1] via sigmoid so the result is interpretable
    as a confidence level.

    Args:
        outcomes: List of P&L values (positive = win, negative = loss).
        lam: Smoothing factor in (0, 1). Higher = more weight on history.

    Returns:
        Confidence in [0, 1]. 0.5 when no data or balanced outcomes.
    """
    if not 0 < lam < 1:
        raise ValueError("lam must be in (0, 1)")
    if not outcomes:
        return 0.5

    ewma = 0.0
    for val in outcomes:
        ewma = lam * ewma + (1 - lam) * val

    # Sigmoid mapping: scale by 0.01 to keep reasonable sensitivity
    x = -0.01 * ewma
    # Clamp to avoid overflow in exp()
    x = max(-500.0, min(500.0, x))
    return 1.0 / (1.0 + math.exp(x))


def risk_appetite(drawdown_pct: float, max_dd_pct: float) -> float:
    """Compute risk appetite factor based on current drawdown.

    Formula: max(0.1, 1 - (dd / max_dd)^2)

    At zero drawdown, appetite is 1.0 (full).
    At max drawdown, appetite is 0.1 (minimum).
    Quadratic decay means appetite drops slowly at first, then sharply.

    Args:
        drawdown_pct: Current drawdown as percentage (0-100).
        max_dd_pct: Maximum tolerable drawdown percentage (must be > 0).

    Returns:
        Risk appetite in [0.1, 1.0].
    """
    if max_dd_pct <= 0:
        raise ValueError("max_dd_pct must be positive")
    if drawdown_pct < 0:
        raise ValueError("drawdown_pct must be non-negative")

    ratio = drawdown_pct / max_dd_pct
    return max(0.1, 1.0 - ratio ** 2)

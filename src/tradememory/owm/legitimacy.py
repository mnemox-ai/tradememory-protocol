"""Decision Legitimacy Gate — evaluate whether an agent has earned the right to trade."""

from __future__ import annotations


# --- Factor scoring functions ---

def _sample_sufficiency(n: int) -> float:
    """Score based on total trade count for this strategy."""
    if n >= 30:
        return 1.0
    if n >= 15:
        return 0.7
    if n >= 5:
        return 0.4
    return 0.1


def _memory_quality(avg_context_drift: float) -> float:
    """Score based on average context drift (lower drift = better)."""
    score = 1.0 - avg_context_drift
    return max(0.0, min(1.0, score))


def _regime_confidence(regime_trade_count: int) -> float:
    """Score based on trades in the current regime."""
    if regime_trade_count >= 10:
        return 1.0
    if regime_trade_count >= 5:
        return 0.7
    if regime_trade_count >= 2:
        return 0.4
    return 0.1


def _streak_state(consecutive_losses: int) -> float:
    """Score based on consecutive loss count."""
    if consecutive_losses == 0:
        return 1.0
    if consecutive_losses <= 2:
        return 0.8
    if consecutive_losses <= 4:
        return 0.5
    return 0.2


def _drawdown_state(drawdown_pct: float) -> float:
    """Score based on account drawdown percentage (0-100 scale)."""
    if drawdown_pct < 5.0:
        return 1.0
    if drawdown_pct < 10.0:
        return 0.7
    if drawdown_pct < 20.0:
        return 0.4
    return 0.1


# --- Weights ---

WEIGHTS = {
    "sample_sufficiency": 0.30,
    "memory_quality": 0.15,
    "regime_confidence": 0.25,
    "streak_state": 0.15,
    "drawdown_state": 0.15,
}


def compute_legitimacy_score(
    strategy_name: str,
    current_regime: str | None,
    memory_count: int,
    avg_context_drift: float,
    win_rate: float | None,
    consecutive_losses: int,
    drawdown_pct: float,
    regime_trade_count: int = 0,
) -> dict:
    """Compute whether an agent has 'earned the right' to trade at full confidence.

    Args:
        strategy_name: Name of the strategy being evaluated.
        current_regime: Current market regime (e.g. "trending_up", "ranging").
        memory_count: Total number of trades for this strategy.
        avg_context_drift: Average context drift score (0-1, lower is better).
        win_rate: Historical win rate (0-1), or None if unknown.
        consecutive_losses: Current consecutive loss streak.
        drawdown_pct: Account drawdown percentage (0-100 scale).
        regime_trade_count: Number of trades in the current regime for this strategy.

    Returns:
        Dict with legitimacy_score, tier, factors, recommendation, position_multiplier.
    """
    factors = {
        "sample_sufficiency": _sample_sufficiency(memory_count),
        "memory_quality": _memory_quality(avg_context_drift),
        "regime_confidence": _regime_confidence(regime_trade_count),
        "streak_state": _streak_state(consecutive_losses),
        "drawdown_state": _drawdown_state(drawdown_pct),
    }

    # Weighted average
    score = sum(factors[k] * WEIGHTS[k] for k in WEIGHTS)

    # Determine tier and multiplier
    if score >= 0.7:
        tier = "full"
        multiplier = 1.0
    elif score >= 0.4:
        tier = "reduced"
        multiplier = 0.5
    else:
        tier = "skip"
        multiplier = 0.0

    # Build recommendation
    recommendation = _build_recommendation(
        tier=tier,
        strategy_name=strategy_name,
        memory_count=memory_count,
        current_regime=current_regime,
        regime_trade_count=regime_trade_count,
        consecutive_losses=consecutive_losses,
        drawdown_pct=drawdown_pct,
        factors=factors,
    )

    return {
        "legitimacy_score": round(score, 4),
        "tier": tier,
        "factors": {k: round(v, 4) for k, v in factors.items()},
        "recommendation": recommendation,
        "position_multiplier": multiplier,
    }


def _build_recommendation(
    *,
    tier: str,
    strategy_name: str,
    memory_count: int,
    current_regime: str | None,
    regime_trade_count: int,
    consecutive_losses: int,
    drawdown_pct: float,
    factors: dict,
) -> str:
    """Build a human-readable recommendation string."""
    if tier == "full":
        return f"{strategy_name}: Full confidence. {memory_count} trades in memory, conditions favorable."

    warnings: list[str] = []

    if factors["sample_sufficiency"] < 0.7:
        warnings.append(f"only {memory_count} trades in memory (need 15+ for confidence)")

    if factors["regime_confidence"] < 0.7:
        regime_str = current_regime or "unknown"
        warnings.append(
            f"only {regime_trade_count} trades in '{regime_str}' regime (need 5+ for confidence)"
        )

    if factors["streak_state"] < 0.8:
        warnings.append(f"{consecutive_losses} consecutive losses")

    if factors["drawdown_state"] < 0.7:
        warnings.append(f"drawdown at {drawdown_pct:.1f}%")

    if factors["memory_quality"] < 0.5:
        warnings.append("high context drift in recent memories")

    warning_text = "; ".join(warnings) if warnings else "multiple factors below threshold"

    if tier == "reduced":
        return f"{strategy_name}: Reduced position size recommended. Issues: {warning_text}."
    else:
        return f"{strategy_name}: Skip this trade. Issues: {warning_text}."

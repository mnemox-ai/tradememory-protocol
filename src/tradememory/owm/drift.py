"""Drift detection for strategy performance and context monitoring.

Includes:
- CUSUM drift detection for win-rate regime changes.
- ΔS context drift monitor for recall relevance scoring.
"""

from __future__ import annotations

import json
import re
from typing import Optional


# ---------------------------------------------------------------------------
# ΔS Context Drift Monitor
# ---------------------------------------------------------------------------

# Zone thresholds — trading domain is stricter than general LLM usage
_ZONE_THRESHOLDS = [
    (0.35, "safe"),
    (0.55, "transit"),
    (0.75, "risk"),
]

_JSON_KEY_FIELDS = {"regime", "atr", "atr_d1", "atr_h1", "symbol", "session",
                    "volatility", "volatility_regime", "direction", "strategy",
                    "spread", "drawdown", "confidence", "timeframe", "hour_utc"}


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase tokens on whitespace/punctuation."""
    return set(re.findall(r"[a-z0-9_.]+", text.lower())) - {"", "none", "null"}


def _extract_from_json(text: str) -> str:
    """If text looks like JSON, extract key fields into a flat string."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text

    if not isinstance(obj, dict):
        return text

    parts: list[str] = []
    for key, value in obj.items():
        key_lower = key.lower()
        # Include known fields or any key that overlaps with our set
        if key_lower in _JSON_KEY_FIELDS or any(f in key_lower for f in _JSON_KEY_FIELDS):
            parts.append(f"{key_lower}_{value}".lower())
        # Also include plain values for generic matching
        if isinstance(value, str):
            parts.append(value.lower())
        elif isinstance(value, (int, float)):
            parts.append(str(value))
    # If we extracted something, return it; otherwise fall back to raw text
    return " ".join(parts) if parts else text


def _detect_regime_warning(memory_ctx: str, current_ctx: str) -> Optional[str]:
    """Generate a specific warning if regime differs between contexts."""
    regimes = {"trending_up", "trending_down", "ranging", "volatile"}

    def _find_regime(text: str) -> Optional[str]:
        text_lower = text.lower()
        for r in regimes:
            if r in text_lower:
                return r
        return None

    mem_regime = _find_regime(memory_ctx)
    cur_regime = _find_regime(current_ctx)

    if mem_regime and cur_regime and mem_regime != cur_regime:
        return f"Regime differs: memory={mem_regime}, current={cur_regime}"
    return None


def compute_context_drift(memory_context: str, current_context: str) -> dict:
    """Compute semantic drift (ΔS) between memory context and current context.

    Uses token overlap (Jaccard similarity) as a lightweight proxy for
    cosine similarity. No external embedding model dependency.

    If either context is a JSON string, key fields (regime, atr, symbol, etc.)
    are extracted before tokenization.

    Args:
        memory_context: The market context stored in memory.
        current_context: The current market context to compare against.

    Returns:
        {
            "delta_s": float (0-1, higher = more drift),
            "zone": str ("safe"|"transit"|"risk"|"danger"),
            "warning": str | None
        }
    """
    # Handle empty/None gracefully
    mem_str = (memory_context or "").strip()
    cur_str = (current_context or "").strip()

    if not mem_str and not cur_str:
        return {"delta_s": 0.0, "zone": "safe", "warning": None}
    if not mem_str or not cur_str:
        return {"delta_s": 1.0, "zone": "danger", "warning": "One context is empty"}

    # Extract from JSON if applicable
    mem_extracted = _extract_from_json(mem_str)
    cur_extracted = _extract_from_json(cur_str)

    # Tokenize
    mem_tokens = _tokenize(mem_extracted)
    cur_tokens = _tokenize(cur_extracted)

    if not mem_tokens and not cur_tokens:
        return {"delta_s": 0.0, "zone": "safe", "warning": None}
    if not mem_tokens or not cur_tokens:
        return {"delta_s": 1.0, "zone": "danger", "warning": "One context produced no tokens"}

    # Jaccard similarity → ΔS = 1 - Jaccard
    intersection = mem_tokens & cur_tokens
    union = mem_tokens | cur_tokens
    jaccard = len(intersection) / len(union)
    delta_s = round(1.0 - jaccard, 4)

    # Classify zone
    zone = "danger"
    for threshold, zone_name in _ZONE_THRESHOLDS:
        if delta_s < threshold:
            zone = zone_name
            break

    # Specific warnings
    warning = _detect_regime_warning(mem_str, cur_str)

    return {"delta_s": delta_s, "zone": zone, "warning": warning}


def compute_drift_summary(drift_results: list[dict]) -> dict:
    """Compute aggregate drift summary across multiple recalled memories.

    Args:
        drift_results: List of dicts from compute_context_drift.

    Returns:
        {
            "avg_delta_s": float,
            "usable_count": int (safe + transit),
            "risky_count": int (risk + danger),
        }
    """
    if not drift_results:
        return {"avg_delta_s": 0.0, "usable_count": 0, "risky_count": 0}

    total = sum(d["delta_s"] for d in drift_results)
    avg = round(total / len(drift_results), 4)
    usable = sum(1 for d in drift_results if d["zone"] in ("safe", "transit"))
    risky = sum(1 for d in drift_results if d["zone"] in ("risk", "danger"))

    return {"avg_delta_s": avg, "usable_count": usable, "risky_count": risky}


def cusum_drift_detect(
    pnl_ratios: list[float],
    target_wr: float = 0.5,
    threshold: float = 4.0,
) -> dict:
    """Detect performance drift using one-sided CUSUM on binary win/loss outcomes.

    Converts pnl_ratios to binary outcomes (1 if > 0, else 0), then applies:
        S_i = max(0, S_{i-1} + (x_i - target_wr))

    Drift is detected when S exceeds threshold, indicating the win rate has
    shifted above the target. For detecting downward drift (degradation),
    pass 1-target_wr or negate the outcomes externally.

    Args:
        pnl_ratios: List of P&L ratios. Positive = win, non-positive = loss.
        target_wr: Expected win rate (default 0.5).
        threshold: CUSUM threshold for drift detection (default 4.0).

    Returns:
        Dict with:
            drift_detected: bool — True if CUSUM exceeded threshold.
            drift_point: int or None — Index where drift was first detected.
            cusum_values: list[float] — Full CUSUM series.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    if not 0 <= target_wr <= 1:
        raise ValueError("target_wr must be between 0 and 1")

    cusum_values: list[float] = []
    s = 0.0
    drift_point = None

    for i, pnl in enumerate(pnl_ratios):
        x = 1.0 if pnl > 0 else 0.0
        s = max(0.0, s + (x - target_wr))
        cusum_values.append(round(s, 6))
        if drift_point is None and s > threshold:
            drift_point = i

    return {
        "drift_detected": drift_point is not None,
        "drift_point": drift_point,
        "cusum_values": cusum_values,
    }

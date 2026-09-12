"""Adapt an Adanos Reddit stock response to TradeMemory sentiment context."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tradememory.data.sentiment import format_sentiment_context


def format_adanos_reddit_context(
    payload: Mapping[str, Any],
    *,
    start_date: str,
    end_date: str,
) -> str:
    """Map Adanos' -1 to +1 sentiment score to the neutral core schema."""

    score = payload.get("sentiment_score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise ValueError("Adanos response must include a numeric sentiment_score")

    if score > 0:
        label = "bullish"
    elif score < 0:
        label = "bearish"
    else:
        label = "neutral"

    return format_sentiment_context(
        {
            "score": score,
            "label": label,
            "sample_window": f"{start_date} to {end_date} UTC",
        },
        source="Adanos Reddit",
    )

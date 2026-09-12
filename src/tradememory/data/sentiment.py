"""Vendor-neutral formatting for sentiment evidence."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any


class SentimentContextError(ValueError):
    """Raised when sentiment evidence does not match the minimal schema."""


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SentimentContextError(f"{field} must be a non-empty string")
    return value.strip()


def _required_score(value: Any) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise SentimentContextError("score must be a finite number")
    return value


def format_sentiment_context(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> str:
    """Format vendor-neutral sentiment evidence for ``market_context``.

    ``payload`` uses a minimal schema:

    - ``score``: finite numeric sentiment score on the provider's documented scale
    - ``label``: human-readable interpretation of the score
    - ``sample_window``: window represented by the sample, including timezone

    ``source`` identifies the provider or dataset. Callers are responsible for
    mapping provider responses to this schema and retaining the provider's score
    semantics in their integration documentation.
    """

    score = _required_score(payload.get("score"))
    label = _required_text(payload.get("label"), "label")
    sample_window = _required_text(payload.get("sample_window"), "sample_window")
    source_name = _required_text(source, "source")

    return f"{source_name} sentiment: {label} (score {score:g}; sample window {sample_window})."

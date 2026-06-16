"""Adanos sentiment helpers for TradeMemory market context.

These helpers intentionally do not call the Adanos API. TradeMemory remains a
local memory server; callers fetch sentiment data themselves and pass the
resulting payload here to build compact context for ``remember_trade``.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

Number = int | float


class AdanosSentimentPayloadError(ValueError):
    """Raised when an Adanos payload cannot be converted to market context."""


def _first_present(payload: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_number(value: Number) -> str:
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(int(value))


def _format_percent(value: float) -> str:
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text}%"


def _format_activity(activity_label: str | None, activity: int | None) -> str | None:
    if activity is None:
        return None
    label = activity_label or "activity"
    return f"{_format_number(activity)} {label}"


def _is_error_payload(payload: Mapping[str, Any]) -> bool:
    error_keys = ("error", "errors", "detail", "message")
    return any(payload.get(key) for key in error_keys)


def normalize_adanos_sentiment(
    payload: Mapping[str, Any],
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """Normalize an Adanos sentiment response for TradeMemory context.

    Args:
        payload: A single response object from an Adanos stock or crypto
            sentiment endpoint.
        source: Optional source label, such as ``"reddit"``, ``"x"``,
            ``"news"``, or ``"polymarket"``.

    Returns:
        A compact dictionary with stable keys that can be embedded into a
        trade's ``market_context`` or formatted with
        :func:`format_adanos_market_context`.
    """

    if _is_error_payload(payload):
        raise AdanosSentimentPayloadError("Adanos sentiment payload contains an error response")

    symbol = _clean_text(_first_present(payload, ("ticker", "symbol", "asset")))
    if symbol is None:
        raise AdanosSentimentPayloadError(
            "Adanos sentiment payload must include a ticker, symbol, or asset"
        )

    name = _clean_text(_first_present(payload, ("company_name", "name", "asset_name")))
    buzz_score = _to_float(payload.get("buzz_score"))
    sentiment_score = _to_float(payload.get("sentiment_score"))
    bullish_pct = _to_float(payload.get("bullish_pct"))
    bearish_pct = _to_float(payload.get("bearish_pct"))
    trend = _clean_text(payload.get("trend"))

    mentions = _to_int(payload.get("mentions"))
    trade_count = _to_int(payload.get("trade_count"))
    activity = mentions if mentions is not None else trade_count
    if mentions is not None:
        activity_label = "mentions"
    elif trade_count is not None:
        activity_label = "trades"
    else:
        activity_label = None

    coverage = _to_int(
        _first_present(
            payload,
            (
                "subreddit_count",
                "unique_posts",
                "unique_tweets",
                "source_count",
                "market_count",
                "unique_traders",
            ),
        )
    )
    engagement = _to_float(_first_present(payload, ("total_upvotes", "total_liquidity")))

    normalized: dict[str, Any] = {"provider": "adanos"}
    source_label = _clean_text(source) or _clean_text(payload.get("source"))
    if source_label:
        normalized["source"] = source_label

    optional_fields = {
        "symbol": symbol,
        "name": name,
        "buzz_score": buzz_score,
        "sentiment_score": sentiment_score,
        "bullish_pct": bullish_pct,
        "bearish_pct": bearish_pct,
        "trend": trend,
        "activity": activity,
        "activity_label": activity_label,
        "coverage": coverage,
        "engagement": engagement,
    }
    normalized.update({key: value for key, value in optional_fields.items() if value is not None})
    return normalized


def format_adanos_market_context(
    payload: Mapping[str, Any],
    *,
    source: str | None = None,
) -> str:
    """Format Adanos sentiment as a concise ``remember_trade`` context string."""

    data = normalize_adanos_sentiment(payload, source=source)
    symbol = data.get("symbol", "asset")
    name = data.get("name")
    source_label = data.get("source")

    subject = f"{symbol} ({name})" if name and name != symbol else str(symbol)
    heading = f"Adanos {source_label} sentiment" if source_label else "Adanos sentiment"
    parts = [f"{heading} for {subject}"]

    if "buzz_score" in data:
        parts.append(f"buzz {_format_number(data['buzz_score'])}/100")
    if "sentiment_score" in data:
        parts.append(f"sentiment score {_format_number(data['sentiment_score'])}")
    if "bullish_pct" in data:
        parts.append(f"{_format_percent(data['bullish_pct'])} bullish")
    if "bearish_pct" in data:
        parts.append(f"{_format_percent(data['bearish_pct'])} bearish")
    if "trend" in data:
        parts.append(f"trend {data['trend']}")

    activity = _format_activity(data.get("activity_label"), data.get("activity"))
    if activity:
        parts.append(activity)
    if "coverage" in data:
        parts.append(f"coverage {_format_number(data['coverage'])}")
    if "engagement" in data:
        parts.append(f"engagement {_format_number(data['engagement'])}")

    return "; ".join(parts) + "."

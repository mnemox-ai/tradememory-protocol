"""Tests for vendor-neutral sentiment context formatting."""

import pytest

from tradememory.data.sentiment import SentimentContextError, format_sentiment_context


def test_format_sentiment_context():
    result = format_sentiment_context(
        {
            "score": 0.23,
            "label": "bullish",
            "sample_window": "2026-07-21 to 2026-07-28 UTC",
        },
        source="Example provider",
    )

    assert result == (
        "Example provider sentiment: bullish "
        "(score 0.23; sample window 2026-07-21 to 2026-07-28 UTC)."
    )


@pytest.mark.parametrize(
    ("payload", "source", "message"),
    [
        (
            {"score": float("nan"), "label": "neutral", "sample_window": "7 days UTC"},
            "provider",
            "score must be a finite number",
        ),
        (
            {"score": 0, "label": "", "sample_window": "7 days UTC"},
            "provider",
            "label must be a non-empty string",
        ),
        (
            {"score": 0, "label": "neutral", "sample_window": ""},
            "provider",
            "sample_window must be a non-empty string",
        ),
        (
            {"score": 0, "label": "neutral", "sample_window": "7 days UTC"},
            " ",
            "source must be a non-empty string",
        ),
    ],
)
def test_format_sentiment_context_rejects_invalid_schema(payload, source, message):
    with pytest.raises(SentimentContextError, match=message):
        format_sentiment_context(payload, source=source)

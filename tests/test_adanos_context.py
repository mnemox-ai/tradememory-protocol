"""Tests for Adanos sentiment context helpers."""

import pytest

from tradememory.data.adanos import (
    AdanosSentimentPayloadError,
    format_adanos_market_context,
    normalize_adanos_sentiment,
)


def test_normalize_stock_sentiment_payload():
    payload = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "buzz_score": 72.45,
        "sentiment_score": 0.38,
        "bullish_pct": 0.64,
        "bearish_pct": 0.21,
        "trend": "rising",
        "mentions": 128,
        "subreddit_count": 6,
        "total_upvotes": 5400,
    }

    result = normalize_adanos_sentiment(payload, source="reddit")

    assert result == {
        "provider": "adanos",
        "source": "reddit",
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "buzz_score": 72.45,
        "sentiment_score": 0.38,
        "bullish_pct": 0.64,
        "bearish_pct": 0.21,
        "trend": "rising",
        "activity": 128,
        "activity_label": "mentions",
        "coverage": 6,
        "engagement": 5400.0,
    }


def test_format_stock_sentiment_context():
    payload = {
        "ticker": "TSLA",
        "company_name": "Tesla",
        "buzz_score": 81.2,
        "bullish_pct": 67.5,
        "trend": "stable",
        "mentions": 240,
        "unique_tweets": 190,
    }

    result = format_adanos_market_context(payload, source="x")

    assert result == (
        "Adanos x sentiment for TSLA (Tesla); buzz 81.2/100; "
        "67.5% bullish; trend stable; 240 mentions; coverage 190."
    )


def test_format_polymarket_activity_context():
    payload = {
        "ticker": "NVDA",
        "buzz_score": 58,
        "sentiment_score": -0.12,
        "trade_count": 42,
        "market_count": 3,
        "total_liquidity": 125000.5,
    }

    result = format_adanos_market_context(payload, source="polymarket")

    assert result == (
        "Adanos polymarket sentiment for NVDA; buzz 58/100; sentiment score -0.12; "
        "42 trades; coverage 3; engagement 125000.5."
    )


def test_format_without_source_uses_clean_fallback():
    assert format_adanos_market_context({"ticker": "AAPL"}) == "Adanos sentiment for AAPL."


def test_format_percent_uses_adanos_zero_to_one_hundred_scale():
    payload = {
        "ticker": "AAPL",
        "bullish_pct": 1,
        "bearish_pct": 0.5,
    }

    result = format_adanos_market_context(payload)

    assert result == "Adanos sentiment for AAPL; 1% bullish; 0.5% bearish."


def test_invalid_optional_values_are_ignored():
    payload = {
        "symbol": "BTC",
        "name": "Bitcoin",
        "buzz_score": "nan",
        "bullish_pct": None,
        "mentions": True,
        "trend": "",
    }

    result = normalize_adanos_sentiment(payload, source="reddit crypto")

    assert result == {
        "provider": "adanos",
        "source": "reddit crypto",
        "symbol": "BTC",
        "name": "Bitcoin",
    }
    assert format_adanos_market_context(payload, source="reddit crypto") == (
        "Adanos reddit crypto sentiment for BTC (Bitcoin)."
    )


def test_error_payload_is_rejected():
    with pytest.raises(AdanosSentimentPayloadError, match="error response"):
        normalize_adanos_sentiment({"detail": "Invalid API key"}, source="reddit")


def test_missing_asset_identifier_is_rejected():
    with pytest.raises(AdanosSentimentPayloadError, match="ticker, symbol, or asset"):
        format_adanos_market_context({"buzz_score": 40}, source="news")

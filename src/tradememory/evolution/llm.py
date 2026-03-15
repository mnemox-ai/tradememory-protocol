"""LLM client abstraction — Protocol + Anthropic implementation.

Design mirrors DataSource Protocol: runtime_checkable, async, swappable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    """Single message in a conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: Optional[str] = None

    def parse_json(self) -> Any:
        """Extract JSON from response content.

        Handles both raw JSON and markdown-wrapped JSON (```json ... ```).
        """
        text = self.content.strip()

        # Try raw JSON first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        if "```" in text:
            # Find JSON block
            for block_marker in ("```json", "```"):
                start = text.find(block_marker)
                if start == -1:
                    continue
                start += len(block_marker)
                end = text.find("```", start)
                if end == -1:
                    continue
                try:
                    return json.loads(text[start:end].strip())
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}...")


class LLMError(Exception):
    """Base error for LLM operations."""

    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""

    def __init__(self, provider: str, retry_after: Optional[float] = None):
        self.retry_after = retry_after
        msg = "Rate limit exceeded"
        if retry_after:
            msg += f" (retry after {retry_after}s)"
        super().__init__(provider, msg)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM providers.

    Implementations:
        - AnthropicClient (Claude API)
        - MockLLMClient (testing)
        - Future: OpenAIClient, LocalModelClient
    """

    @property
    def name(self) -> str:
        """Provider name (e.g. 'anthropic', 'openai')."""
        ...

    async def complete(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """Send messages and get a completion.

        Args:
            messages: Conversation history (user/assistant turns).
            model: Model ID override (None = provider default).
            temperature: Sampling temperature (0.0-1.0).
            max_tokens: Max output tokens.
            system: System prompt (separate from messages).

        Returns:
            LLMResponse with content and usage stats.

        Raises:
            LLMError: On API errors.
            LLMRateLimitError: On rate limit (429).
        """
        ...

    async def close(self) -> None:
        """Clean up resources."""
        ...


class AnthropicClient:
    """Claude API client via anthropic SDK.

    Uses ANTHROPIC_API_KEY from environment.
    Default model: claude-sonnet-4-20250514 (Sonnet first, not Opus — 10x cost diff).
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        self._default_model = default_model or self.DEFAULT_MODEL
        self._api_key = api_key
        self._client = None

    @property
    def name(self) -> str:
        return "anthropic"

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise LLMError(
                    "anthropic",
                    "anthropic package not installed. Run: pip install anthropic",
                )
            kwargs = {}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = anthropic.AsyncAnthropic(**kwargs)
        return self._client

    async def complete(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: Optional[str] = None,
    ) -> LLMResponse:
        client = self._get_client()
        model_id = model or self._default_model

        # Convert to Anthropic format
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        try:
            response = await client.messages.create(**kwargs)
        except Exception as e:
            error_str = str(e)
            if "rate_limit" in error_str.lower() or "429" in error_str:
                raise LLMRateLimitError("anthropic")
            raise LLMError("anthropic", f"API error: {error_str}") from e

        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None


class MockLLMClient:
    """Mock LLM client for testing. Returns pre-configured responses."""

    def __init__(self, responses: Optional[list[str]] = None):
        self._responses = list(responses) if responses else []
        self._call_count = 0
        self.calls: list[dict] = []  # record all calls for assertion
        self.should_error: bool = False
        self.error_message: str = "Mock error"

    @property
    def name(self) -> str:
        return "mock"

    async def complete(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: Optional[str] = None,
    ) -> LLMResponse:
        self.calls.append({
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system": system,
        })

        if self.should_error:
            self._call_count += 1
            raise LLMError("mock", self.error_message)

        if self._call_count < len(self._responses):
            content = self._responses[self._call_count]
        else:
            content = '{"patterns": []}'

        self._call_count += 1

        return LLMResponse(
            content=content,
            model=model or "mock-model",
            input_tokens=100,
            output_tokens=200,
        )

    async def close(self) -> None:
        pass

"""Unified LLM client supporting DeepSeek and Claude via instructor library."""

import logging
import os
from typing import TypeVar

from tradememory.replay.models import AgentDecision, DecisionType, ReplayConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Cost per million tokens (USD)
_COST_TABLE = {
    "deepseek": {"input": 0.27, "output": 1.10},
    "claude": {"input": 3.00, "output": 15.00},  # sonnet default
}

# Per-model cost overrides (for non-default models)
_MODEL_COST_TABLE = {
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-haiku-4-5-20250315": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
}

_DEFAULT_MODELS = {
    "deepseek": "deepseek-chat",
    "claude": "claude-sonnet-4-20250514",
}


_DEFAULT_API_KEY_ENV = {
    "deepseek": "DEEPSEEK_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}


class LLMClient:
    """Unified LLM client wrapping DeepSeek (OpenAI-compatible) and Claude Sonnet."""

    def __init__(self, config: ReplayConfig) -> None:
        try:
            import instructor
            from anthropic import Anthropic
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                f"Missing dependency for replay module: {e}. "
                "Install with: pip install tradememory-protocol[replay]"
            ) from e

        self.provider = config.llm_provider
        self.model = config.llm_model or _DEFAULT_MODELS[self.provider]
        self.total_tokens_used: int = 0
        self.total_cost_usd: float = 0.0

        # Auto-detect correct env var if user didn't override
        if config.api_key_env == "DEEPSEEK_API_KEY" and self.provider == "claude":
            env_var = _DEFAULT_API_KEY_ENV["claude"]
        else:
            env_var = config.api_key_env

        api_key = os.environ.get(env_var)
        if not api_key:
            raise RuntimeError(
                f"API key not found. Set environment variable {env_var} "
                f"for provider '{self.provider}'."
            )

        if self.provider == "deepseek":
            self.client = instructor.from_openai(
                OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            )
        elif self.provider == "claude":
            self.client = instructor.from_anthropic(Anthropic(api_key=api_key))
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def decide(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T] = AgentDecision,
        temperature: float = 0.3,
        max_tokens: int = 0,  # 0 = auto: 4096 for DeepSeek, 1024 for Claude
    ) -> T:
        """Call LLM and return structured AgentDecision (or fallback HOLD on error)."""
        if max_tokens == 0:
            # DeepSeek generates verbose reasoning traces (~3000 tokens)
            max_tokens = 4096 if self.provider == "deepseek" else 1024
        try:
            if self.provider == "deepseek":
                result, completion = self.client.chat.completions.create_with_completion(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_model=response_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                usage = completion.usage
                if usage:
                    input_tokens = usage.prompt_tokens or 0
                    output_tokens = usage.completion_tokens or 0
                    self._track_cost(input_tokens, output_tokens)

            else:  # claude
                result, raw = self.client.messages.create_with_completion(
                    model=self.model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    response_model=response_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if raw.usage:
                    self._track_cost(raw.usage.input_tokens, raw.usage.output_tokens)

            return result

        except Exception as e:
            logger.error(f"LLM API error ({self.provider}): {e}")
            return AgentDecision(
                market_observation="API error — no market data available",
                reasoning_trace=f"LLM API call failed: {e}",
                decision=DecisionType.HOLD,
                confidence=0.0,
            )

    def _track_cost(self, input_tokens: int, output_tokens: int) -> None:
        total = input_tokens + output_tokens
        self.total_tokens_used += total
        # Use model-specific costs if available, else provider default
        costs = _MODEL_COST_TABLE.get(self.model, _COST_TABLE[self.provider])
        self.total_cost_usd += (
            input_tokens * costs["input"] + output_tokens * costs["output"]
        ) / 1_000_000

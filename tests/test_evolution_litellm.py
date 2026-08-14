"""Unit tests for the LiteLLM evolution client + provider factory.

litellm is an optional extra; these tests patch litellm.acompletion so they run
without hitting a real provider.
"""

from types import SimpleNamespace

import pytest

from tradememory.evolution.llm import (
    AnthropicClient,
    LiteLLMClient,
    LLMClient,
    LLMError,
    LLMMessage,
    LLMRateLimitError,
    create_llm_client,
)


def _fake_response(content: str = '{"patterns": []}'):
    """Build a minimal object shaped like a litellm ModelResponse."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=22)
    return SimpleNamespace(choices=[choice], usage=usage, model="gpt-4o-mini")


@pytest.fixture
def captured(monkeypatch):
    """Patch litellm.acompletion and capture the kwargs it was called with."""
    import litellm

    calls: list[dict] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return _fake_response()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return calls


class TestLiteLLMClient:
    def test_satisfies_llm_client_protocol(self):
        assert isinstance(LiteLLMClient(), LLMClient)

    def test_name(self):
        assert LiteLLMClient().name == "litellm"

    @pytest.mark.asyncio
    async def test_complete_dispatches_openai_shaped_call(self, captured):
        client = LiteLLMClient(default_model="anthropic/claude-sonnet-4-20250514")
        resp = await client.complete(
            [LLMMessage(role="user", content="hi")],
            temperature=0.3,
            max_tokens=256,
            system="be terse",
        )

        assert len(captured) == 1
        kwargs = captured[0]
        assert kwargs["model"] == "anthropic/claude-sonnet-4-20250514"
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 256
        # system is sent as the first message (OpenAI chat shape)
        assert kwargs["messages"][0] == {"role": "system", "content": "be terse"}
        assert kwargs["messages"][1] == {"role": "user", "content": "hi"}

        # response parsed back through LLMResponse
        assert resp.content == '{"patterns": []}'
        assert resp.input_tokens == 11
        assert resp.output_tokens == 22
        assert resp.stop_reason == "stop"

    @pytest.mark.asyncio
    async def test_drop_params_true_by_default(self, captured):
        await LiteLLMClient().complete([LLMMessage(role="user", content="hi")])
        assert captured[0]["drop_params"] is True

    @pytest.mark.asyncio
    async def test_drop_params_can_be_disabled(self, captured):
        await LiteLLMClient(drop_params=False).complete(
            [LLMMessage(role="user", content="hi")]
        )
        assert captured[0]["drop_params"] is False

    @pytest.mark.asyncio
    async def test_credentials_omitted_when_unset(self, captured):
        await LiteLLMClient().complete([LLMMessage(role="user", content="hi")])
        assert "api_key" not in captured[0]
        assert "base_url" not in captured[0]

    @pytest.mark.asyncio
    async def test_credentials_forwarded_when_set(self, captured):
        await LiteLLMClient(
            api_key="sk-test", base_url="http://localhost:4000/v1"
        ).complete([LLMMessage(role="user", content="hi")])
        assert captured[0]["api_key"] == "sk-test"
        assert captured[0]["base_url"] == "http://localhost:4000/v1"

    @pytest.mark.asyncio
    async def test_model_override_wins(self, captured):
        await LiteLLMClient(default_model="gpt-4o-mini").complete(
            [LLMMessage(role="user", content="hi")], model="openai/gpt-4o"
        )
        assert captured[0]["model"] == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_rate_limit_maps_to_rate_limit_error(self, monkeypatch):
        import litellm

        class RateLimitError(Exception):
            pass

        async def boom(**kwargs):
            raise RateLimitError("429 too many requests")

        monkeypatch.setattr(litellm, "acompletion", boom)
        with pytest.raises(LLMRateLimitError):
            await LiteLLMClient().complete([LLMMessage(role="user", content="hi")])

    @pytest.mark.asyncio
    async def test_other_errors_map_to_llm_error(self, monkeypatch):
        import litellm

        async def boom(**kwargs):
            raise ValueError("bad request")

        monkeypatch.setattr(litellm, "acompletion", boom)
        with pytest.raises(LLMError):
            await LiteLLMClient().complete([LLMMessage(role="user", content="hi")])


class TestCreateLLMClient:
    def test_defaults_to_anthropic(self, monkeypatch):
        monkeypatch.delenv("TRADEMEMORY_LLM_PROVIDER", raising=False)
        assert isinstance(create_llm_client(), AnthropicClient)

    def test_env_var_selects_litellm(self, monkeypatch):
        monkeypatch.setenv("TRADEMEMORY_LLM_PROVIDER", "litellm")
        assert isinstance(create_llm_client(), LiteLLMClient)

    def test_explicit_arg_overrides_env(self, monkeypatch):
        monkeypatch.setenv("TRADEMEMORY_LLM_PROVIDER", "anthropic")
        assert isinstance(create_llm_client("litellm"), LiteLLMClient)

    def test_claude_alias_maps_to_anthropic(self, monkeypatch):
        monkeypatch.delenv("TRADEMEMORY_LLM_PROVIDER", raising=False)
        assert isinstance(create_llm_client("claude"), AnthropicClient)

    def test_kwargs_forwarded(self, monkeypatch):
        monkeypatch.delenv("TRADEMEMORY_LLM_PROVIDER", raising=False)
        client = create_llm_client("litellm", default_model="openai/gpt-4o")
        assert isinstance(client, LiteLLMClient)
        assert client._default_model == "openai/gpt-4o"

    def test_unknown_provider_raises(self, monkeypatch):
        monkeypatch.delenv("TRADEMEMORY_LLM_PROVIDER", raising=False)
        with pytest.raises(LLMError):
            create_llm_client("no-such-provider")

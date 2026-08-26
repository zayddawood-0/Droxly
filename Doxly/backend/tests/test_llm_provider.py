import pytest
from pydantic import BaseModel

from app.ai.llm import (
    AnthropicLLMProvider,
    FakeLLMProvider,
    Message,
    StructuredOutputError,
    get_llm_provider,
)
from app.core.config import settings


class _Foo(BaseModel):
    x: int


async def test_generate_returns_a_queued_response_in_order():
    provider = FakeLLMProvider(responses=["first", "second"])
    first = await provider.generate(
        [Message("user", "hi")], system_prompt="sys", model_tier="fast"
    )
    second = await provider.generate(
        [Message("user", "hi")], system_prompt="sys", model_tier="fast"
    )
    assert first.text == "first"
    assert second.text == "second"


async def test_generate_falls_back_to_the_default_response_when_queue_is_empty():
    provider = FakeLLMProvider(default_response="fallback")
    completion = await provider.generate(
        [Message("user", "hi")], system_prompt="sys", model_tier="standard"
    )
    assert completion.text == "fallback"


async def test_stream_yields_the_generated_text_word_by_word():
    provider = FakeLLMProvider(responses=["hello world"])
    chunks = [
        chunk
        async for chunk in provider.stream(
            [Message("user", "hi")], system_prompt="sys", model_tier="fast"
        )
    ]
    assert "".join(chunks).strip() == "hello world"


async def test_generate_structured_returns_the_queued_pydantic_object():
    provider = FakeLLMProvider(structured_responses=[_Foo(x=42)])
    completion = await provider.generate_structured(
        [Message("user", "hi")],
        system_prompt="sys",
        output_schema=_Foo,
        model_tier="standard",
    )
    assert completion.result.x == 42
    assert completion.input_tokens > 0
    assert completion.output_tokens > 0
    assert completion.model == "fake-standard"


async def test_generate_structured_can_be_scripted_to_raise():
    provider = FakeLLMProvider(
        structured_responses=[StructuredOutputError("bad output")]
    )
    with pytest.raises(StructuredOutputError):
        await provider.generate_structured(
            [Message("user", "hi")],
            system_prompt="sys",
            output_schema=_Foo,
            model_tier="standard",
        )


async def test_generate_structured_raises_when_nothing_is_queued():
    provider = FakeLLMProvider()
    with pytest.raises(StructuredOutputError):
        await provider.generate_structured(
            [Message("user", "hi")],
            system_prompt="sys",
            output_schema=_Foo,
            model_tier="standard",
        )


def test_get_llm_provider_defaults_to_fake(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "fake")
    assert isinstance(get_llm_provider(), FakeLLMProvider)


def test_get_llm_provider_requires_an_api_key_for_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    with pytest.raises(RuntimeError):
        get_llm_provider()


def test_get_llm_provider_returns_anthropic_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-key")
    assert isinstance(get_llm_provider(), AnthropicLLMProvider)


# --- R5 audit finding #1 (NFR-OBS-001) — AnthropicLLMProvider.generate_structured
# must preserve real, already-metered usage even when the structured-output
# gate fails after a successful HTTP call, not just on success. `_call` is
# mocked (rather than the httpx wire layer) since it already encapsulates the
# full HTTP round-trip and returns the exact `payload` shape every downstream
# branch operates on. ---


def _anthropic_provider() -> AnthropicLLMProvider:
    return AnthropicLLMProvider(api_key="sk-test-key")


async def test_generate_structured_success_returns_real_usage_from_anthropic(
    monkeypatch,
):
    provider = _anthropic_provider()

    async def _fake_call(self, *args, **kwargs):
        return {
            "model": "claude-sonnet-5",
            "usage": {"input_tokens": 123, "output_tokens": 45},
            "content": [{"type": "tool_use", "name": "emit_result", "input": {"x": 7}}],
        }

    monkeypatch.setattr(AnthropicLLMProvider, "_call", _fake_call)

    completion = await provider.generate_structured(
        [Message("user", "hi")],
        system_prompt="sys",
        output_schema=_Foo,
        model_tier="standard",
    )

    assert completion.result.x == 7
    assert completion.input_tokens == 123
    assert completion.output_tokens == 45
    assert completion.model == "claude-sonnet-5"


async def test_generate_structured_missing_tool_use_preserves_real_usage(monkeypatch):
    """A successful HTTP response with no tool_use block (the model declined
    to call the forced tool) must not discard the usage that response
    already carried."""
    provider = _anthropic_provider()

    async def _fake_call(self, *args, **kwargs):
        return {
            "model": "claude-sonnet-5",
            "usage": {"input_tokens": 123, "output_tokens": 45},
            "content": [{"type": "text", "text": "I decline to use the tool."}],
        }

    monkeypatch.setattr(AnthropicLLMProvider, "_call", _fake_call)

    with pytest.raises(StructuredOutputError) as exc_info:
        await provider.generate_structured(
            [Message("user", "hi")],
            system_prompt="sys",
            output_schema=_Foo,
            model_tier="standard",
        )

    assert exc_info.value.input_tokens == 123
    assert exc_info.value.output_tokens == 45
    assert exc_info.value.model == "claude-sonnet-5"


async def test_generate_structured_invalid_payload_preserves_real_usage(monkeypatch):
    """A successful HTTP response whose tool_use input fails Pydantic
    validation against output_schema must also preserve the real usage
    that response already carried."""
    provider = _anthropic_provider()

    async def _fake_call(self, *args, **kwargs):
        return {
            "model": "claude-sonnet-5",
            "usage": {"input_tokens": 123, "output_tokens": 45},
            "content": [
                {
                    "type": "tool_use",
                    "name": "emit_result",
                    "input": {"not_x": "wrong shape"},
                }
            ],
        }

    monkeypatch.setattr(AnthropicLLMProvider, "_call", _fake_call)

    with pytest.raises(StructuredOutputError) as exc_info:
        await provider.generate_structured(
            [Message("user", "hi")],
            system_prompt="sys",
            output_schema=_Foo,
            model_tier="standard",
        )

    assert exc_info.value.input_tokens == 123
    assert exc_info.value.output_tokens == 45
    assert exc_info.value.model == "claude-sonnet-5"


def test_structured_output_error_defaults_usage_to_none_when_not_given():
    """A caller-constructed instance with no usage info (e.g. a test
    double) must never fabricate values — confirms the default stays None,
    not 0 or an estimate."""
    error = StructuredOutputError("bad output")
    assert error.input_tokens is None
    assert error.output_tokens is None
    assert error.model is None

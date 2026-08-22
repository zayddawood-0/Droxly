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
    result = await provider.generate_structured(
        [Message("user", "hi")],
        system_prompt="sys",
        output_schema=_Foo,
        model_tier="standard",
    )
    assert result.x == 42


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

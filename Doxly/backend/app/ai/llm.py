import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, cast

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings

ModelTier = Literal["fast", "standard"]

# decisions.md OQ-02, resolved at Phase 8 implementation time (its own
# "Status: Assumption — revisit at Phase 8/9" note): callers request a tier,
# never a model ID (ai.md §2) — this table is the one place a model
# upgrade happens, matching every node's cost/latency tiering in
# langgraph.md's node design.
ANTHROPIC_MODEL_IDS: dict[ModelTier, str] = {
    "fast": "claude-haiku-4-5-20251001",
    "standard": "claude-sonnet-5",
}


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass(frozen=True)
class StructuredCompletion[T: BaseModel]:
    """
    R5 remediation (`NFR-OBS-001`) — `generate_structured`'s original return
    shape was the bare validated `T`, with no usage data at all, unlike
    `generate()`'s `Completion`. That made it impossible for any caller
    (the Extraction Agent node being the first real one) to log real
    input/output token counts for a structured-output call. Mirrors
    `Completion` exactly, wrapping the validated result alongside real
    provider-reported usage so callers get both without a second call.
    """

    result: T
    input_tokens: int
    output_tokens: int
    model: str


class StructuredOutputError(Exception):
    """
    Raised by `generate_structured` when the provider's constrained output
    still isn't valid JSON, or doesn't validate against `output_schema`
    (ai.md §5's "two gates, not one"). A graph's Validation node catches
    this to decide bounded retry vs. terminal failure (langgraph.md §1.5) —
    this is not itself a retry decision.

    R5 audit finding #1 (`NFR-OBS-001`): a provider HTTP call can succeed
    (and report real `input_tokens`/`output_tokens`) even when the
    *structured-output* gate fails afterward (no `tool_use` block, or one
    that fails Pydantic validation) — that usage was already real and
    metered, and must not be discarded just because this exception is
    raised instead of a `StructuredCompletion`. `input_tokens`/
    `output_tokens`/`model` default to `None` (never fabricated) for the
    genuine case where no HTTP response was ever received at all (a
    network-level failure propagates as a different exception entirely,
    never reaches here) or for a caller-constructed instance (e.g.
    `FakeLLMProvider`'s test double) that has no usage to report.
    """

    def __init__(
        self,
        message: str,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model


class LLMProvider(ABC):
    """ai.md §2 — every AI operation is written against this interface, never a vendor SDK directly (decisions.md ADR-011)."""

    provider_name: str

    @abstractmethod
    async def generate(
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Completion:
        """Single-shot, non-streamed completion — used by worker-run graph nodes."""

    @abstractmethod
    def stream(
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Token-by-token streaming — used only by the inline chat path (Answer Generator)."""

    @abstractmethod
    async def generate_structured[T: BaseModel](
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        output_schema: type[T],
        model_tier: ModelTier,
    ) -> StructuredCompletion[T]:
        """
        ai.md §5: provider-constrained output, then validated against
        `output_schema` with Pydantic before the caller ever sees it.
        Raises StructuredOutputError if either gate fails.
        """


class FakeLLMProvider(LLMProvider):
    """
    Deterministic, offline, zero-cost — the active default (mirrors
    decisions.md OQ-03's Phase 6 resolution for embeddings) and the
    documented approach for graph node tests (testing.md §4.1: "every node
    ... unit-tested independently, with the LLM call mocked"). Scriptable:
    a test queues up the exact responses it wants returned, in call order;
    with no queue, a caller-supplied (or generic) default response is used
    every time.
    """

    provider_name = "fake"

    def __init__(
        self,
        *,
        responses: list[str] | None = None,
        structured_responses: list[BaseModel | Exception] | None = None,
        default_response: str = "This is a fake response for testing.",
    ) -> None:
        self._responses = list(responses or [])
        self._structured_responses = list(structured_responses or [])
        self._default_response = default_response
        self.calls: list[dict] = []

    async def generate(
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Completion:
        self.calls.append(
            {
                "messages": messages,
                "model_tier": model_tier,
                "system_prompt": system_prompt,
            }
        )
        text = self._responses.pop(0) if self._responses else self._default_response
        return Completion(
            text=text,
            input_tokens=sum(len(m.content.split()) for m in messages),
            output_tokens=len(text.split()),
            model=f"fake-{model_tier}",
        )

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        completion = await self.generate(
            messages,
            system_prompt=system_prompt,
            model_tier=model_tier,
            max_tokens=max_tokens,
        )
        for word in completion.text.split(" "):
            yield word + " "

    async def generate_structured[T: BaseModel](
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        output_schema: type[T],
        model_tier: ModelTier,
    ) -> StructuredCompletion[T]:
        self.calls.append(
            {
                "messages": messages,
                "model_tier": model_tier,
                "system_prompt": system_prompt,
                "structured": True,
            }
        )
        if self._structured_responses:
            next_response = self._structured_responses.pop(0)
            if isinstance(next_response, Exception):
                raise next_response
            # Test double: the caller queues responses matching the schema it
            # requests, but that contract isn't expressible in the queue's
            # own (necessarily erased) storage type.
            result = cast(T, next_response)
            return StructuredCompletion(
                result=result,
                input_tokens=sum(len(m.content.split()) for m in messages),
                output_tokens=len(str(result.model_dump()).split()),
                model=f"fake-{model_tier}",
            )
        raise StructuredOutputError(
            "FakeLLMProvider has no queued structured_responses for this call."
        )


class AnthropicLLMProvider(LLMProvider):
    """Real completions via Anthropic's REST Messages API (decisions.md ADR-011 default)."""

    provider_name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def generate(
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Completion:
        payload = await self._call(
            messages, system_prompt, model_tier, max_tokens, temperature
        )
        text = "".join(
            block["text"] for block in payload["content"] if block["type"] == "text"
        )
        return Completion(
            text=text,
            input_tokens=payload["usage"]["input_tokens"],
            output_tokens=payload["usage"]["output_tokens"],
            model=payload["model"],
        )

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        async with (
            httpx.AsyncClient(timeout=60.0) as client,
            client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers=self._headers(),
                json=self._request_body(
                    messages, system_prompt, model_tier, max_tokens, 0.0, stream=True
                ),
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[len("data: ") :])
                if event.get("type") == "content_block_delta":
                    yield event["delta"].get("text", "")

    async def generate_structured[T: BaseModel](
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        output_schema: type[T],
        model_tier: ModelTier,
    ) -> StructuredCompletion[T]:
        # Forced tool-choice is Anthropic's native structured-output
        # mechanism (ai.md §5 step 2) — the schema becomes a single tool
        # the model is required to call.
        tool = {
            "name": "emit_result",
            "description": "Return the extracted/generated result.",
            "input_schema": output_schema.model_json_schema(),
        }
        payload = await self._call(
            messages,
            system_prompt,
            model_tier,
            max_tokens=2048,
            temperature=0.0,
            tools=[tool],
            tool_choice={"type": "tool", "name": "emit_result"},
        )
        # R5 audit finding #1 — a successful HTTP response already carries
        # real, metered usage regardless of whether the structured-output
        # gate below succeeds; both failure branches attach it to the
        # raised StructuredOutputError so a caller (e.g. the Extraction
        # Agent node) can still log real ai_requests token counts on a
        # structural failure, instead of losing already-known data.
        usage = payload["usage"]
        input_tokens = usage["input_tokens"]
        output_tokens = usage["output_tokens"]
        model = payload["model"]

        tool_use = next(
            (block for block in payload["content"] if block["type"] == "tool_use"), None
        )
        if tool_use is None:
            raise StructuredOutputError(
                "Provider did not return a tool_use block.",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
            )
        try:
            result = output_schema.model_validate(tool_use["input"])
        except ValidationError as error:
            raise StructuredOutputError(
                str(error),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
            ) from error
        return StructuredCompletion(
            result=result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _request_body(
        self,
        messages: Sequence[Message],
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int,
        temperature: float,
        *,
        stream: bool = False,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
    ) -> dict:
        body: dict = {
            "model": ANTHROPIC_MODEL_IDS[model_tier],
            "system": system_prompt,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools
        if tool_choice:
            body["tool_choice"] = tool_choice
        return body

    async def _call(
        self,
        messages: Sequence[Message],
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int,
        temperature: float,
        *,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
    ) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=self._headers(),
                json=self._request_body(
                    messages,
                    system_prompt,
                    model_tier,
                    max_tokens,
                    temperature,
                    tools=tools,
                    tool_choice=tool_choice,
                ),
            )
            response.raise_for_status()
            return response.json()


def get_llm_provider() -> LLMProvider:
    """Single construction point — the only place `settings.llm_provider` is read."""
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set."
            )
        return AnthropicLLMProvider(settings.anthropic_api_key)
    return FakeLLMProvider()

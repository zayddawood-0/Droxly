"""
`LLMProvider` decorator that logs one `ai_requests` row per actual
`generate()`/`generate_structured()` call — `observability.md` §4's literal
"every call to an LLM or embedding provider is logged" (`NFR-OBS-001`),
rather than the "one row per run" shape R4 (chat) and R5 (extraction) use
(already committed/audited, left unchanged — out of scope to retroactively
fix). First built for R6 (Comparison, whose `difference_detection_node`
can make many real calls in a single run) and reused as-is for R7
(Summarization, whose map-reduce strategy has the same shape) — extracted
to this shared module once a second concrete need existed, per
`CLAUDE.md`'s "three concrete implementations beat one speculative
abstraction": duplicating this correctness-sensitive usage-preservation/
error-isolation logic a second time would have meant two copies that could
silently drift, not a genuine second implementation.
"""

import logging
import time
import uuid
from collections.abc import Sequence

from pydantic import BaseModel

from app.ai.llm import (
    Completion,
    LLMProvider,
    Message,
    ModelTier,
    StructuredCompletion,
    StructuredOutputError,
)
from app.repositories.observability_repository import AiRequestRepository

logger = logging.getLogger(__name__)


class ObservedLLMProvider(LLMProvider):
    """Wraps a real `LLMProvider` so every `generate()`/`generate_structured()`
    call writes its own `ai_requests` row (`operation` is fixed per instance —
    one per caller, e.g. `"comparison"` or `"summarization"`)."""

    def __init__(
        self,
        llm: LLMProvider,
        ai_request_repo: AiRequestRepository,
        user_id: uuid.UUID,
        operation: str,
    ) -> None:
        self._llm = llm
        self._ai_request_repo = ai_request_repo
        self._user_id = user_id
        self._operation = operation
        self.provider_name = llm.provider_name

    async def generate(
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Completion:
        start = time.monotonic()
        try:
            completion = await self._llm.generate(
                messages,
                system_prompt=system_prompt,
                model_tier=model_tier,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception:
            await self._log(
                status="error",
                error_code="generation_failed",
                input_tokens=None,
                output_tokens=None,
                model="n/a",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            raise
        await self._log(
            status="success",
            error_code=None,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            model=completion.model,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return completion

    def stream(
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        model_tier: ModelTier,
        max_tokens: int = 1024,
    ):
        # Not used by any background-worker graph (ai.md §2: "used only by
        # the inline chat path") — delegated unchanged, not itself observed,
        # matching this provider's sole real use (worker-run graphs).
        return self._llm.stream(
            messages,
            system_prompt=system_prompt,
            model_tier=model_tier,
            max_tokens=max_tokens,
        )

    async def generate_structured[T: BaseModel](
        self,
        messages: Sequence[Message],
        *,
        system_prompt: str,
        output_schema: type[T],
        model_tier: ModelTier,
    ) -> StructuredCompletion[T]:
        start = time.monotonic()
        try:
            completion = await self._llm.generate_structured(
                messages,
                system_prompt=system_prompt,
                output_schema=output_schema,
                model_tier=model_tier,
            )
        except StructuredOutputError as exc:
            await self._log(
                status="error",
                error_code="structured_output_failed",
                input_tokens=exc.input_tokens,
                output_tokens=exc.output_tokens,
                model=exc.model or "n/a",
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            raise
        await self._log(
            status="success",
            error_code=None,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            model=completion.model,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return completion

    async def _log(
        self,
        *,
        status: str,
        error_code: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        model: str,
        latency_ms: int,
    ) -> None:
        try:
            await self._ai_request_repo.create(
                self._user_id,
                operation=self._operation,
                provider=self.provider_name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
            )
        except Exception:  # noqa: BLE001 — best-effort logging, mirrors R3/R5
            logger.warning(
                "ai_request_log_failed",
                extra={"user_id": str(self._user_id), "operation": self._operation},
            )

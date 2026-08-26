"""
tasks/remediation-plan.md R6 — the worker-invoked half of comparison
(skills/backend.md §12: "the worker job entrypoint reuses the same service
layer as the API, never a parallel code path" — mirrors
ExtractionProcessingService's role from R5).

AI observability design (R6 audit-equivalent finding, resolved before
implementation via explicit user sign-off): `observability.md` §4 states
`NFR-OBS-001` verbatim as "every call to an LLM or embedding provider is
logged" — one `ai_requests` row per real provider call, not per graph run.
R4 (chat) and R5 (extraction) instead log one row per *run* (using only the
last/decisive call's tokens) — an already-committed, already-audited
precedent this task does not retroactively change (out of scope), but does
not repeat here either: `difference_detection_node` can make many real
`generate()` calls in a single comparison (one per modified segment), so
collapsing them into a single logged row would be far lossier here than it
already is for chat/extraction. `ObservedLLMProvider` (`app/ai/
observed_llm_provider.py`, shared with R7's `SummaryProcessingService`) and
`_ObservedEmbeddingProvider` below wrap the real providers so every actual
call — however many a run makes — writes its own row, without threading an
`AiRequestRepository` through every graph node function individually.
"""

import logging
import time
import uuid

from app.ai.embeddings import EmbeddingProvider
from app.ai.graphs.comparison import (
    ComparisonState,
    DocumentSegment,
    build_comparison_graph,
)
from app.ai.llm import LLMProvider
from app.ai.observed_llm_provider import ObservedLLMProvider
from app.document_processing.chunking import count_tokens
from app.repositories.comparison_repository import ComparisonRepository
from app.repositories.document_repository import DocumentChunkRepository
from app.repositories.observability_repository import AiRequestRepository

logger = logging.getLogger(__name__)

# langgraph.md §5: "if alignment_confidence falls below a defined threshold
# ... degraded-report terminal state" already covers "low" (ALIGNMENT_
# CONFIDENCE_THRESHOLD, comparison.py). No spec-defined split exists for
# "high" vs. "medium" among aligned (non-degraded) comparisons — this is a
# response-shaping/display concern, not graph business logic, so it lives
# here rather than in the graph itself. 0.75 is chosen the same way
# ALIGNMENT_CONFIDENCE_THRESHOLD was: a documented, defensible default (a
# comparison "solidly more alike than not" on average best-match similarity
# vs. one "clearly and consistently alike"), not a spec-mandated number —
# revisitable like any other tuned threshold.
HIGH_ALIGNMENT_THRESHOLD = 0.75

_DEGRADED_MESSAGE = (
    "These documents are too structurally different to produce a "
    "meaningful comparison."
)
EMPTY_COMPARISON_RESULT: dict = {
    "alignment_quality": "low",
    "message": None,
    "additions": [],
    "deletions": [],
    "modifications": [],
}


class _ObservedEmbeddingProvider(EmbeddingProvider):
    """Wraps a real `EmbeddingProvider` so every `embed_batch()` call writes
    its own `ai_requests` row. `input_tokens` uses `count_tokens()` — the
    same real `tiktoken` `cl100k_base` encoding `document_processing/
    chunking.py` already documents as matching what the embedding model
    actually sees (real accounting, not an estimate — `embed_batch`'s own
    return value carries no usage data to relay instead, the same
    structural gap `AnthropicLLMProvider`'s equivalent had before R5's
    `generate_structured` fix, out of scope to also close here)."""

    def __init__(
        self,
        embeddings: EmbeddingProvider,
        ai_request_repo: AiRequestRepository,
        user_id: uuid.UUID,
    ) -> None:
        self._embeddings = embeddings
        self._ai_request_repo = ai_request_repo
        self._user_id = user_id
        self.model_name = embeddings.model_name
        self.provider_name = embeddings.provider_name

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        start = time.monotonic()
        input_tokens = sum(count_tokens(text) for text in texts)
        try:
            vectors = await self._embeddings.embed_batch(texts)
        except Exception:
            await self._log(
                status="error",
                error_code="embedding_failed",
                input_tokens=input_tokens,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            raise
        await self._log(
            status="success",
            error_code=None,
            input_tokens=input_tokens,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        return vectors

    async def _log(
        self,
        *,
        status: str,
        error_code: str | None,
        input_tokens: int,
        latency_ms: int,
    ) -> None:
        try:
            await self._ai_request_repo.create(
                self._user_id,
                operation="embedding",
                provider=self.provider_name,
                model=self.model_name,
                input_tokens=input_tokens,
                output_tokens=None,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
            )
        except Exception:  # noqa: BLE001 — best-effort logging, mirrors R3/R5
            logger.warning(
                "comparison.ai_request_log_failed",
                extra={"user_id": str(self._user_id), "operation": "embedding"},
            )


def _to_result_json(final_state: dict) -> dict:
    """api.md §7's `ComparisonResult` shape, persisted verbatim into
    `comparisons.result_json` (database.md §3.12)."""
    if final_state.get("degraded"):
        return {**EMPTY_COMPARISON_RESULT, "message": _DEGRADED_MESSAGE}

    confidence = final_state.get("alignment_confidence") or 0.0
    alignment_quality = "high" if confidence >= HIGH_ALIGNMENT_THRESHOLD else "medium"

    additions: list[dict] = []
    deletions: list[dict] = []
    modifications: list[dict] = []
    for diff in final_state.get("classified_changes") or []:
        if diff.type == "addition":
            additions.append(
                {"document": "b", "page_number": diff.page_b, "excerpt": diff.segment_b}
            )
        elif diff.type == "deletion":
            deletions.append(
                {"document": "a", "page_number": diff.page_a, "excerpt": diff.segment_a}
            )
        else:
            modifications.append(
                {
                    "change_type": diff.category or "wording",
                    "a_page_number": diff.page_a,
                    "a_excerpt": diff.segment_a,
                    "b_page_number": diff.page_b,
                    "b_excerpt": diff.segment_b,
                    "explanation": diff.description,
                }
            )

    return {
        "alignment_quality": alignment_quality,
        "message": None,
        "additions": additions,
        "deletions": deletions,
        "modifications": modifications,
    }


class ComparisonProcessingService:
    def __init__(
        self,
        comparison_repo: ComparisonRepository,
        chunk_repo: DocumentChunkRepository,
        ai_request_repo: AiRequestRepository,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.comparison_repo = comparison_repo
        self.chunk_repo = chunk_repo
        self.ai_request_repo = ai_request_repo
        self.llm_provider = llm_provider
        self.embedding_provider = embedding_provider

    async def run_comparison(
        self, user_id: uuid.UUID, comparison_id: uuid.UUID
    ) -> None:
        """Idempotent against a stray/duplicate job delivery the same way
        `ExtractionProcessingService.run_extraction` is: a missing
        comparison or one no longer `processing` is a silent no-op."""
        comparison = await self.comparison_repo.get(user_id, comparison_id)
        if comparison is None or comparison.status != "processing":
            return

        segments_a, text_a = await self._load_segments(
            user_id, comparison.document_a_id
        )
        segments_b, text_b = await self._load_segments(
            user_id, comparison.document_b_id
        )

        observed_llm = ObservedLLMProvider(
            self.llm_provider, self.ai_request_repo, user_id, operation="comparison"
        )
        observed_embeddings = _ObservedEmbeddingProvider(
            self.embedding_provider, self.ai_request_repo, user_id
        )
        graph = build_comparison_graph(observed_llm, observed_embeddings)

        initial_state: ComparisonState = {
            "user_id": user_id,
            "document_a_id": comparison.document_a_id,
            "document_b_id": comparison.document_b_id,
            "text_a": text_a,
            "text_b": text_b,
            "segments_a": segments_a,
            "segments_b": segments_b,
        }
        final_state = await graph.ainvoke(
            initial_state, config={"configurable": {"thread_id": str(comparison_id)}}
        )

        if final_state["status"] == "success":
            result_json = _to_result_json(final_state)
            await self.comparison_repo.set_result(
                user_id, comparison_id, status="completed", result_json=result_json
            )
        else:
            await self.comparison_repo.set_result(
                user_id,
                comparison_id,
                status="failed",
                result_json=dict(EMPTY_COMPARISON_RESULT),
            )

    async def _load_segments(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> tuple[list[DocumentSegment], str]:
        chunks = await self.chunk_repo.list_for_document(user_id, document_id)
        segments: list[DocumentSegment] = [
            {"content": chunk.content, "page_number": chunk.page_number}
            for chunk in chunks
        ]
        text = "\n".join(chunk.content for chunk in chunks)
        return segments, text

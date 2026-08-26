"""
tasks/remediation-plan.md R7 — the worker-invoked half of summarization
(skills/backend.md §12: "the worker job entrypoint reuses the same service
layer as the API, never a parallel code path" — mirrors
ExtractionProcessingService/ComparisonProcessingService's role from
R5/R6).

AI observability: per `observability.md` §4's literal `NFR-OBS-001` ("every
call to an LLM or embedding provider is logged"), reuses the same
`ObservedLLMProvider` (`app/ai/observed_llm_provider.py`) R6 built and this
task extracted to a shared module — the Summarization graph's map-reduce
strategy can make many real `generate()` calls in a single run (one per
document chunk, plus one final combine call) and up to 3 real
`generate_structured()` quality-check calls (the bounded retry budget,
langgraph.md §3), so every one of them gets its own `ai_requests` row
(`operation="summarization"`), never collapsed into a single row.
"""

import uuid

from app.ai.graphs.summarization import SummarizationState, build_summarization_graph
from app.ai.llm import LLMProvider
from app.ai.observed_llm_provider import ObservedLLMProvider
from app.repositories.document_repository import DocumentChunkRepository
from app.repositories.observability_repository import AiRequestRepository
from app.repositories.summary_repository import DocumentSummaryRepository


class SummaryProcessingService:
    def __init__(
        self,
        summary_repo: DocumentSummaryRepository,
        chunk_repo: DocumentChunkRepository,
        ai_request_repo: AiRequestRepository,
        llm_provider: LLMProvider,
    ) -> None:
        self.summary_repo = summary_repo
        self.chunk_repo = chunk_repo
        self.ai_request_repo = ai_request_repo
        self.llm_provider = llm_provider

    async def run_summary(self, user_id: uuid.UUID, summary_id: uuid.UUID) -> None:
        """Idempotent against a stray/duplicate job delivery the same way
        `ExtractionProcessingService.run_extraction`/`ComparisonProcessingService.
        run_comparison` are: a missing summary or one no longer `processing`
        is a silent no-op."""
        summary = await self.summary_repo.get(user_id, summary_id)
        if summary is None or summary.status != "processing":
            return

        document_text = await self._load_document_text(user_id, summary.document_id)

        observed_llm = ObservedLLMProvider(
            self.llm_provider, self.ai_request_repo, user_id, operation="summarization"
        )
        graph = build_summarization_graph(observed_llm)

        initial_state: SummarizationState = {
            "user_id": user_id,
            "document_id": summary.document_id,
            "summary_type": summary.summary_type,  # type: ignore[typeddict-item]
            "document_text": document_text,
            "retry_count": 0,
        }
        final_state = await graph.ainvoke(
            initial_state, config={"configurable": {"thread_id": str(summary_id)}}
        )

        if final_state["status"] == "success":
            await self.summary_repo.set_result(
                user_id,
                summary_id,
                status="completed",
                content=final_state["draft_summary"],
            )
        else:
            await self.summary_repo.set_result(
                user_id, summary_id, status="failed", content=None
            )

    async def _load_document_text(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> str:
        chunks = await self.chunk_repo.list_for_document(user_id, document_id)
        return "\n\n".join(chunk.content for chunk in chunks)

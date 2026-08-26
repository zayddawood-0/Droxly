"""
tasks/remediation-plan.md R5 — the worker-invoked half of extraction
(skills/backend.md §12: "the worker job entrypoint reuses the same service
layer as the API, never a parallel code path" — `app/workers/
extraction_worker.py` is a thin wrapper around `run_extraction` below, the
same way `document_processing_worker.py` wraps
`DocumentProcessingService.process_document`).
"""

import logging
import time
import uuid

from app.ai.graphs.extraction import ExtractionState, build_extraction_graph
from app.ai.llm import LLMProvider
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.observability_repository import AiRequestRepository
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

_EXTRACTION_FAILED_ERROR_CODE = "extraction_failed"


def _to_result_json(validated_result: dict) -> list[dict]:
    """
    api.md §6's `result` shape, persisted verbatim into `extractions.
    result_json` (database.md §3.11) so `GET /extractions/{id}` can read it
    straight off the row with no further transformation. `original_value`
    is the one field this shape carries beyond the API response (api.md
    PATCH: "the model's original value is retained internally ... but not
    surfaced in this response") — `ExtractionDetailResponse` deliberately
    has no such field, so it round-trips out cleanly.
    """
    return [
        {
            "field": name,
            "value": field["value"],
            "original_value": field["value"],
            "confidence": field.get("confidence"),
            "not_found_reason": (
                field.get("reason") if not field.get("found", True) else None
            ),
            "citation": (
                {
                    "page_number": field.get("source_page"),
                    "snippet": field["source_snippet"],
                }
                if field.get("source_snippet")
                else None
            ),
            "corrected": False,
        }
        for name, field in validated_result.items()
    ]


class ExtractionProcessingService:
    def __init__(
        self,
        extraction_repo: ExtractionRepository,
        ai_request_repo: AiRequestRepository,
        llm_provider: LLMProvider,
        retrieval_service: RetrievalService,
    ) -> None:
        self.extraction_repo = extraction_repo
        self.ai_request_repo = ai_request_repo
        self.llm_provider = llm_provider
        self.retrieval_service = retrieval_service

    async def run_extraction(
        self, user_id: uuid.UUID, extraction_id: uuid.UUID
    ) -> None:
        """
        Idempotent against a stray/duplicate job delivery the same way
        `DocumentProcessingService.process_document` is: a missing
        extraction (deleted before the job ran) or one no longer
        `processing` (already terminal — this job is a re-delivery of an
        already-completed attempt) is a silent no-op, not an error.
        """
        extraction = await self.extraction_repo.get(user_id, extraction_id)
        if extraction is None or extraction.status != "processing":
            return

        graph = build_extraction_graph(self.llm_provider, self.retrieval_service)
        initial_state: ExtractionState = {
            "user_id": user_id,
            "document_id": extraction.document_id,
            "template_key": extraction.template_key,
            "requested_schema": extraction.schema_json,
            "retry_count": 0,
        }
        start = time.monotonic()
        final_state = await graph.ainvoke(
            initial_state, config={"configurable": {"thread_id": str(extraction_id)}}
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        if final_state["status"] == "success":
            result_json = _to_result_json(final_state["validated_result"])
            await self.extraction_repo.set_result(
                user_id, extraction_id, status="completed", result_json=result_json
            )
        else:
            await self.extraction_repo.set_result(
                user_id, extraction_id, status="failed", result_json=[]
            )

        await self._log_ai_request(user_id, final_state, latency_ms)

    async def _log_ai_request(
        self, user_id: uuid.UUID, final_state: dict, latency_ms: int
    ) -> None:
        """
        `NFR-OBS-001` — one `ai_requests` row per extraction run
        (`operation="extraction"`), mirroring `chat_service.py`'s "one row
        per turn" shape: the Extraction Agent's own structured-output call
        is the run's real cost driver (the Document Classifier's
        preliminary FAST-tier call is dropped from the logged row the same
        way chat drops its classifier's tokens once Answer Generator runs)
        — real provider-reported tokens when the agent call succeeded at
        least once, `None`/`"n/a"` if it never did (a total structural
        failure). A failure logging this row must never affect the
        extraction's own already-decided outcome, above.
        """
        success = final_state["status"] == "success"
        try:
            await self.ai_request_repo.create(
                user_id,
                operation="extraction",
                provider=self.llm_provider.provider_name,
                model=final_state.get("extraction_model") or "n/a",
                input_tokens=final_state.get("extraction_input_tokens"),
                output_tokens=final_state.get("extraction_output_tokens"),
                latency_ms=latency_ms,
                status="success" if success else "error",
                error_code=None if success else _EXTRACTION_FAILED_ERROR_CODE,
            )
        except Exception:  # noqa: BLE001 — best-effort logging, see docstring above
            logger.warning(
                "extraction.ai_request_log_failed", extra={"user_id": str(user_id)}
            )

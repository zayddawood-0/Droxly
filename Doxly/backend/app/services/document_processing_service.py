"""
tasks/remediation-plan.md R3 — FR-PROC-001..004. Orchestrates
extract -> chunk -> embed -> status transitions (document-processing.md
§5/§10, architecture.md §4's sequence diagram), reusing chunking.py
(FR-PROC-002) and the existing EmbeddingProvider (FR-PROC-003) unmodified.
Called identically by the API-adjacent worker job (workers/
document_processing_worker.py) and would be called the same way by any
future inline caller — skills/backend.md §12: "the worker job entrypoint
reuses the same service layer as the API, never a parallel code path."
"""

import asyncio
import logging
import time
import uuid

from app.ai.embeddings import EmbeddingProvider
from app.core.storage import StorageProvider
from app.document_processing.base import (
    DocumentParseError,
    ParsedCsv,
    ParsedText,
    UnsupportedContentError,
)
from app.document_processing.chunking import chunk_csv_rows, chunk_text
from app.document_processing.parser_registry import get_parser
from app.errors import EmptyDocumentError
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.repositories.observability_repository import AiRequestRepository

logger = logging.getLogger(__name__)

# document-processing.md §4/§6 — the sanitized message for the one
# degenerate-input failure mode that isn't itself a DocumentParseError
# (rag.md §2's "near-empty extracted text yields zero chunks" case, shared
# across DOCX/TXT/CSV rather than each parser inventing its own wording).
_EMPTY_DOCUMENT_MESSAGE = (
    "This document appears to have no extractable text to process."
)


class DocumentProcessingService:
    def __init__(
        self,
        document_repo: DocumentRepository,
        chunk_repo: DocumentChunkRepository,
        storage_provider: StorageProvider,
        embedding_provider: EmbeddingProvider,
        ai_request_repo: AiRequestRepository,
    ) -> None:
        self.document_repo = document_repo
        self.chunk_repo = chunk_repo
        self.storage_provider = storage_provider
        self.embedding_provider = embedding_provider
        self.ai_request_repo = ai_request_repo

    async def process_document(
        self, user_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """
        Idempotent and retry-safe (NFR-AVAIL-002, FR-PROC-005): clears any
        chunks a prior, incompletely-finished attempt may have already
        written before writing the fresh set, so a retry never appends
        duplicate/inconsistent rows. A document that's already `ready` is
        treated as a no-op (a stray duplicate job delivery), and a missing
        document (deleted before the job ran) is silently skipped — neither
        is a processing failure.

        Raises only for a *transient* failure (`TransientParseError` or any
        non-`DocumentParseError` exception) — the caller (workers/
        document_processing_worker.py) lets that propagate into RQ's own
        retry policy. Every permanent, content-inherent failure is caught
        here and terminates the document as `failed` without raising.
        """
        document = await self.document_repo.get(user_id, document_id)
        if document is None or document.status == "ready":
            return

        try:
            await self.document_repo.set_status(
                user_id, document_id, status="extracting"
            )
            data = await self.storage_provider.read_object_bytes(document.storage_key)
            parser = get_parser(document.mime_type)

            if not parser.sniff_matches(data[:16]):
                raise UnsupportedContentError()

            loop = asyncio.get_running_loop()
            parsed = await loop.run_in_executor(None, parser.parse, data)

            await self.document_repo.set_status(user_id, document_id, status="chunking")
            if isinstance(parsed, ParsedCsv):
                text_chunks = chunk_csv_rows(parsed.header, parsed.rows)
            else:
                assert isinstance(parsed, ParsedText)
                text_chunks = chunk_text(
                    parsed.full_text, page_breaks=parsed.page_breaks
                )

            if not text_chunks:
                raise EmptyDocumentError(document_id)

            if isinstance(parsed, ParsedText) and parsed.page_count is not None:
                document.page_count = parsed.page_count

            await self.document_repo.set_status(
                user_id, document_id, status="embedding"
            )
            vectors = await self._embed_with_observability(user_id, text_chunks)

            await self.chunk_repo.delete_for_document(user_id, document_id)
            await self.chunk_repo.bulk_create(
                user_id,
                document_id,
                [
                    {
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "page_number": chunk.page_number,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                        "token_count": chunk.token_count,
                        "embedding": vector,
                        "embedding_model": self.embedding_provider.model_name,
                    }
                    for chunk, vector in zip(text_chunks, vectors, strict=True)
                ],
            )

            document.extracted_text_available = True
            await self.document_repo.session.flush()
            await self.document_repo.set_status(user_id, document_id, status="ready")

        except DocumentParseError as exc:
            if exc.retryable:
                raise
            await self.document_repo.set_status(
                user_id,
                document_id,
                status="failed",
                processing_error=exc.user_message,
            )
        except EmptyDocumentError:
            await self.document_repo.set_status(
                user_id,
                document_id,
                status="failed",
                processing_error=_EMPTY_DOCUMENT_MESSAGE,
            )

    async def _embed_with_observability(
        self, user_id: uuid.UUID, text_chunks: list
    ) -> list[list[float]]:
        """
        R3 remediation (`NFR-OBS-001`, P0) — every embedding provider call
        writes one `ai_requests` row (`operation="embedding"`), success and
        failure alike, mirroring the pattern `chat_service.py` already
        established for LLM calls (`observability.md` §4). `input_tokens`
        reuses each chunk's already-computed `token_count` — real data, not
        an estimate; embedding has no "generated" tokens, so
        `output_tokens` stays `None` (the column is nullable for exactly
        this kind of operation-specific gap, `database.md` §3.13).
        """
        input_tokens = sum(chunk.token_count for chunk in text_chunks)
        status = "success"
        error_code: str | None = None
        start = time.monotonic()
        try:
            return await self.embedding_provider.embed_batch(
                [chunk.content for chunk in text_chunks]
            )
        except Exception:
            status = "error"
            error_code = "embedding_failed"
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            await self._log_ai_request(
                user_id,
                status=status,
                error_code=error_code,
                input_tokens=input_tokens,
                latency_ms=latency_ms,
            )

    async def _log_ai_request(
        self,
        user_id: uuid.UUID,
        *,
        status: str,
        error_code: str | None,
        input_tokens: int,
        latency_ms: int,
    ) -> None:
        """
        A failure writing this observability row must never turn an
        otherwise-successful embedding call into a failed document (or vice
        versa) — the embedding call's own outcome, already decided by
        `_embed_with_observability`'s `try`/`except`/`raise`, is
        unaffected by whatever happens here.
        """
        try:
            await self.ai_request_repo.create(
                user_id,
                operation="embedding",
                provider=self.embedding_provider.provider_name,
                model=self.embedding_provider.model_name,
                input_tokens=input_tokens,
                output_tokens=None,
                latency_ms=latency_ms,
                status=status,
                error_code=error_code,
            )
        except Exception:  # noqa: BLE001 — best-effort logging, see docstring above
            logger.warning(
                "document_processing.ai_request_log_failed",
                extra={"user_id": str(user_id), "operation": "embedding"},
            )

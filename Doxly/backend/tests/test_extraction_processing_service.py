"""
tasks/remediation-plan.md R5 — ExtractionProcessingService, the
worker-invoked half of extraction (mirrors test_document_processing_
service.py's shape: real Postgres via `db_session`, real RetrievalService,
FakeEmbeddingProvider, and a scripted FakeLLMProvider — no RQ/queue
involved, this exercises the graph-running orchestration directly).
"""

import uuid

from sqlalchemy import select

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.graphs.extraction import PRESET_TEMPLATES
from app.ai.llm import FakeLLMProvider, StructuredOutputError
from app.models import Document, DocumentChunk
from app.models.observability import AiRequest
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.observability_repository import AiRequestRepository
from app.services.extraction_processing_service import ExtractionProcessingService
from app.services.retrieval_service import RetrievalService
from tests.conftest import make_user

INVOICE_TEXT = "Invoice #123 dated 2026-01-01 from Acme Corp, total $500."


async def _make_ready_document_with_chunk(db_session, user_id, *, content: str):
    document = Document(
        user_id=user_id,
        file_name="invoice.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="ready",
    )
    db_session.add(document)
    await db_session.flush()
    provider = FakeEmbeddingProvider()
    [vector] = await provider.embed_batch([content])
    db_session.add(
        DocumentChunk(
            user_id=user_id,
            document_id=document.id,
            chunk_index=0,
            content=content,
            page_number=1,
            char_start=0,
            char_end=len(content),
            token_count=len(content.split()),
            embedding=vector,
            embedding_model=provider.model_name,
        )
    )
    await db_session.flush()
    return document


def _build_service(db_session, llm: FakeLLMProvider) -> ExtractionProcessingService:
    embedding_provider = FakeEmbeddingProvider()
    document_repo = DocumentRepository(db_session)
    retrieval = RetrievalService(
        DocumentChunkRepository(db_session), document_repo, embedding_provider
    )
    return ExtractionProcessingService(
        ExtractionRepository(db_session),
        AiRequestRepository(db_session),
        llm,
        retrieval,
    )


def _invoice_result_model():
    from app.ai.graphs.extraction import ExtractedField, _build_result_model

    result_model = _build_result_model(PRESET_TEMPLATES["invoice"]["fields"])
    return result_model(
        invoice_number=ExtractedField(value="123", confidence=0.9, source_page=1),
        invoice_date=ExtractedField(value="2026-01-01", confidence=0.9, source_page=1),
        vendor_name=ExtractedField(
            value="Acme Corp",
            confidence=0.9,
            source_page=1,
            source_snippet=INVOICE_TEXT,
        ),
        total_amount=ExtractedField(value="500", confidence=0.9, source_page=1),
        due_date=ExtractedField(
            value=None, found=False, reason="not mentioned in the document"
        ),
    )


async def test_successful_extraction_persists_completed_result_and_logs_ai_request(
    db_session,
):
    user = await make_user(db_session)
    document = await _make_ready_document_with_chunk(
        db_session, user.id, content=INVOICE_TEXT
    )
    extraction = await ExtractionRepository(db_session).create(
        user.id,
        document_id=document.id,
        template_key="invoice",
        schema_json=PRESET_TEMPLATES["invoice"]["fields"],
        result_json=[],
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=["invoice"], structured_responses=[_invoice_result_model()]
    )
    service = _build_service(db_session, llm)

    await service.run_extraction(user.id, extraction.id)

    updated = await ExtractionRepository(db_session).get(user.id, extraction.id)
    assert updated.status == "completed"
    by_field = {item["field"]: item for item in updated.result_json}
    assert by_field["vendor_name"]["value"] == "Acme Corp"
    assert by_field["vendor_name"]["citation"] == {
        "page_number": 1,
        "snippet": INVOICE_TEXT,
    }
    assert by_field["due_date"]["value"] is None
    assert by_field["due_date"]["not_found_reason"] == "not mentioned in the document"
    assert by_field["due_date"]["citation"] is None
    assert all(item["corrected"] is False for item in updated.result_json)
    assert all("original_value" in item for item in updated.result_json)

    rows = (
        (
            await db_session.execute(
                select(AiRequest).where(
                    AiRequest.user_id == user.id, AiRequest.operation == "extraction"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "fake"
    assert row.status == "success"
    assert row.error_code is None
    assert row.input_tokens is not None and row.input_tokens > 0
    assert row.output_tokens is not None and row.output_tokens > 0
    assert row.model == "fake-standard"


async def test_terminal_structural_failure_persists_failed_status_and_logs_error(
    db_session,
):
    user = await make_user(db_session)
    document = await _make_ready_document_with_chunk(
        db_session, user.id, content=INVOICE_TEXT
    )
    extraction = await ExtractionRepository(db_session).create(
        user.id,
        document_id=document.id,
        template_key="invoice",
        schema_json=PRESET_TEMPLATES["invoice"]["fields"],
        result_json=[],
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=["invoice"],
        structured_responses=[
            StructuredOutputError("malformed"),
            StructuredOutputError("still malformed"),
        ],
    )
    service = _build_service(db_session, llm)

    await service.run_extraction(user.id, extraction.id)

    updated = await ExtractionRepository(db_session).get(user.id, extraction.id)
    assert updated.status == "failed"
    assert updated.result_json == []

    rows = (
        (
            await db_session.execute(
                select(AiRequest).where(
                    AiRequest.user_id == user.id, AiRequest.operation == "extraction"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "error"
    assert row.error_code == "extraction_failed"
    # A total structural failure means the Extraction Agent's structured
    # call never returned usable usage data — logged as unavailable, never
    # fabricated (mirrors R3's "output_tokens=None" precedent for a gap
    # that's genuinely absent, not estimated).
    assert row.input_tokens is None
    assert row.output_tokens is None
    assert row.model == "n/a"


async def test_missing_extraction_is_silently_skipped(db_session):
    user = await make_user(db_session)
    llm = FakeLLMProvider()
    service = _build_service(db_session, llm)

    await service.run_extraction(user.id, uuid.uuid4())  # must not raise

    rows = (
        (
            await db_session.execute(
                select(AiRequest).where(AiRequest.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []


async def test_already_terminal_extraction_is_a_no_op(db_session):
    """Guards against a stray/duplicate job delivery re-running an
    already-completed extraction (NFR-AVAIL-002-adjacent idempotency, same
    shape as DocumentProcessingService's "already ready" guard)."""
    user = await make_user(db_session)
    document = await _make_ready_document_with_chunk(
        db_session, user.id, content=INVOICE_TEXT
    )
    extraction = await ExtractionRepository(db_session).create(
        user.id,
        document_id=document.id,
        template_key="invoice",
        schema_json=PRESET_TEMPLATES["invoice"]["fields"],
        result_json=[{"field": "invoice_number", "value": "already done"}],
        status="completed",
    )
    llm = FakeLLMProvider()  # no responses queued — would raise if actually invoked
    service = _build_service(db_session, llm)

    await service.run_extraction(user.id, extraction.id)  # must not raise

    unchanged = await ExtractionRepository(db_session).get(user.id, extraction.id)
    assert unchanged.status == "completed"
    assert unchanged.result_json == [
        {"field": "invoice_number", "value": "already done"}
    ]


async def test_ai_request_logging_failure_does_not_affect_extraction_outcome(
    db_session,
):
    user = await make_user(db_session)
    document = await _make_ready_document_with_chunk(
        db_session, user.id, content=INVOICE_TEXT
    )
    extraction = await ExtractionRepository(db_session).create(
        user.id,
        document_id=document.id,
        template_key="invoice",
        schema_json=PRESET_TEMPLATES["invoice"]["fields"],
        result_json=[],
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=["invoice"], structured_responses=[_invoice_result_model()]
    )
    embedding_provider = FakeEmbeddingProvider()
    document_repo = DocumentRepository(db_session)
    retrieval = RetrievalService(
        DocumentChunkRepository(db_session), document_repo, embedding_provider
    )

    class _FailingAiRequestRepository(AiRequestRepository):
        async def create(self, user_id, **fields):
            raise RuntimeError("observability store unavailable")

    service = ExtractionProcessingService(
        ExtractionRepository(db_session),
        _FailingAiRequestRepository(db_session),
        llm,
        retrieval,
    )

    await service.run_extraction(user.id, extraction.id)  # must not raise

    updated = await ExtractionRepository(db_session).get(user.id, extraction.id)
    assert updated.status == "completed"

"""
tasks/remediation-plan.md R5 — workers/extraction_worker.py. Mirrors
test_document_processing_worker.py's shape exactly: real Postgres, real
(committed) rows, `process_document_job`'s own sync-entrypoint pattern
(`asyncio.run` internally) applies identically here, so this file uses the
same plain-sync-`def`-test / real-commit convention, not the `db_session`
SAVEPOINT fixture.
"""

import asyncio
import uuid

from sqlalchemy import delete

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.graphs.extraction import (
    PRESET_TEMPLATES,
    ExtractedField,
    _build_result_model,
)
from app.ai.llm import FakeLLMProvider
from app.core.database import async_session_factory, engine
from app.models import Document, DocumentChunk, Extraction, User
from app.repositories.extraction_repository import ExtractionRepository
from app.workers import extraction_worker
from app.workers.extraction_worker import on_extraction_failure, run_extraction_job

INVOICE_TEXT = "Invoice #123 dated 2026-01-01 from Acme Corp, total $500."


def _run(coro):
    """See test_document_processing_worker.py's `_run` for the full
    rationale — required whenever a test itself calls a real sync RQ
    entrypoint (`asyncio.run()` internally) from an already-async-capable
    test process."""

    async def _wrapped():
        await engine.dispose()
        result = await coro
        await engine.dispose()
        return result

    return asyncio.run(_wrapped())


def _dispose_engine_before_and_after_sync_entrypoint_call():
    class _Guard:
        def __enter__(self):
            asyncio.run(engine.dispose())
            return self

        def __exit__(self, *exc_info):
            asyncio.run(engine.dispose())
            return False

    return _Guard()


async def _create_user_document_and_extraction(*, status: str = "processing"):
    async with async_session_factory() as session:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            display_name="Extraction Worker Test User",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.flush()
        document = Document(
            user_id=user.id,
            file_name="invoice.pdf",
            storage_key=f"documents/{user.id}/{uuid.uuid4()}",
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="a" * 64,
            status="ready",
        )
        session.add(document)
        await session.flush()
        embedding_provider = FakeEmbeddingProvider()
        [vector] = await embedding_provider.embed_batch([INVOICE_TEXT])
        session.add(
            DocumentChunk(
                user_id=user.id,
                document_id=document.id,
                chunk_index=0,
                content=INVOICE_TEXT,
                page_number=1,
                char_start=0,
                char_end=len(INVOICE_TEXT),
                token_count=len(INVOICE_TEXT.split()),
                embedding=vector,
                embedding_model=embedding_provider.model_name,
            )
        )
        extraction = Extraction(
            user_id=user.id,
            document_id=document.id,
            template_key="invoice",
            schema_json=PRESET_TEMPLATES["invoice"]["fields"],
            result_json=[],
            status=status,
        )
        session.add(extraction)
        await session.commit()
        return user.id, document.id, extraction.id


async def _cleanup(user_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(delete(Extraction).where(Extraction.user_id == user_id))
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.user_id == user_id)
        )
        await session.execute(delete(Document).where(Document.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _fetch_extraction(
    user_id: uuid.UUID, extraction_id: uuid.UUID
) -> Extraction | None:
    async with async_session_factory() as session:
        return await ExtractionRepository(session).get(user_id, extraction_id)


def _invoice_result_model():
    result_model = _build_result_model(PRESET_TEMPLATES["invoice"]["fields"])
    return result_model(
        invoice_number=ExtractedField(value="123", confidence=0.9, source_page=1),
        invoice_date=ExtractedField(value="2026-01-01", confidence=0.9, source_page=1),
        vendor_name=ExtractedField(value="Acme Corp", confidence=0.9, source_page=1),
        total_amount=ExtractedField(value="500", confidence=0.9, source_page=1),
        due_date=ExtractedField(
            value=None, found=False, reason="not mentioned in the document"
        ),
    )


def test_run_extraction_job_completes_the_full_pipeline(monkeypatch):
    scripted_llm = FakeLLMProvider(
        responses=["invoice"], structured_responses=[_invoice_result_model()]
    )
    monkeypatch.setattr(extraction_worker, "get_llm_provider", lambda: scripted_llm)

    user_id, _document_id, extraction_id = _run(_create_user_document_and_extraction())
    try:
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_extraction_job(str(user_id), str(extraction_id))

        extraction = _run(_fetch_extraction(user_id, extraction_id))
        assert extraction.status == "completed"
        by_field = {item["field"]: item for item in extraction.result_json}
        assert by_field["vendor_name"]["value"] == "Acme Corp"
    finally:
        _run(_cleanup(user_id))


def test_run_extraction_job_unexpected_error_propagates_and_does_not_mark_failed(
    monkeypatch,
):
    """
    An unexpected provider-level failure (a raw exception, not a
    StructuredOutputError the graph already routes to a terminal `failed`
    state internally) must propagate so RQ's own retry mechanism sees it —
    mirrors process_document_job's identical transient-failure contract.
    """

    class _BrokenLLMProvider(FakeLLMProvider):
        async def generate(self, *args, **kwargs):
            raise RuntimeError("provider connection reset")

    monkeypatch.setattr(
        extraction_worker, "get_llm_provider", lambda: _BrokenLLMProvider()
    )

    user_id, _document_id, extraction_id = _run(_create_user_document_and_extraction())
    try:
        try:
            with _dispose_engine_before_and_after_sync_entrypoint_call():
                run_extraction_job(str(user_id), str(extraction_id))
            raise AssertionError("expected run_extraction_job to raise")
        except RuntimeError:
            pass

        extraction = _run(_fetch_extraction(user_id, extraction_id))
        assert extraction.status == "processing"  # untouched by this attempt alone
    finally:
        _run(_cleanup(user_id))


def test_on_extraction_failure_is_a_noop_while_retries_remain():
    from types import SimpleNamespace

    job = SimpleNamespace(should_retry=True, args=("ignored", "ignored"))
    on_extraction_failure(job, None, None, None, None)  # must not touch any row


def test_on_extraction_failure_marks_extraction_failed_once_retries_are_exhausted():
    from types import SimpleNamespace

    user_id, _document_id, extraction_id = _run(_create_user_document_and_extraction())
    try:
        job = SimpleNamespace(
            should_retry=False, args=(str(user_id), str(extraction_id))
        )
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            on_extraction_failure(job, None, None, None, None)

        extraction = _run(_fetch_extraction(user_id, extraction_id))
        assert extraction.status == "failed"
        assert extraction.result_json == []
    finally:
        _run(_cleanup(user_id))


def test_run_extraction_job_never_touches_another_users_extraction(monkeypatch):
    """Cross-tenant category (testing.md §3.5) applied to the worker
    entrypoint itself: a stray job carrying a mismatched user_id/extraction_id
    pair must be a silent no-op (mirrors ExtractionProcessingService's own
    tenant-scoped `get` guard), never touch the real owner's row."""
    scripted_llm = FakeLLMProvider(
        responses=["invoice"], structured_responses=[_invoice_result_model()]
    )
    monkeypatch.setattr(extraction_worker, "get_llm_provider", lambda: scripted_llm)

    owner_id, _document_id, extraction_id = _run(_create_user_document_and_extraction())
    try:
        attacker_id = uuid.uuid4()
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_extraction_job(str(attacker_id), str(extraction_id))

        extraction = _run(_fetch_extraction(owner_id, extraction_id))
        assert extraction.status == "processing"  # untouched by the wrong-tenant call
    finally:
        _run(_cleanup(owner_id))

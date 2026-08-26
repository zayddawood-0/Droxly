"""
tasks/remediation-plan.md R7 — workers/summary_worker.py. Mirrors
test_comparison_worker.py's shape exactly: real Postgres, real (committed)
rows, the real sync RQ entrypoint (`asyncio.run` internally), so this file
uses the same plain-sync-`def`-test / real-commit convention, not the
`db_session` SAVEPOINT fixture.
"""

import asyncio
import uuid

from sqlalchemy import delete

from app.ai.graphs.summarization import QualityCheckResult
from app.ai.llm import FakeLLMProvider
from app.core.database import async_session_factory, engine
from app.models import Document, DocumentChunk, DocumentSummary, User
from app.repositories.summary_repository import DocumentSummaryRepository
from app.workers import summary_worker
from app.workers.summary_worker import on_summary_failure, run_summary_job


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


async def _create_user_document_and_summary(*, status: str = "processing"):
    async with async_session_factory() as session:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            display_name="Summary Worker Test User",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.flush()

        document = Document(
            user_id=user.id,
            file_name="doc.pdf",
            storage_key=f"documents/{user.id}/{uuid.uuid4()}",
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="a" * 64,
            status="ready",
        )
        session.add(document)
        await session.flush()
        content = "A modest document about quarterly performance."
        session.add(
            DocumentChunk(
                user_id=user.id,
                document_id=document.id,
                chunk_index=0,
                content=content,
                page_number=1,
                char_start=0,
                char_end=len(content),
                token_count=len(content.split()),
                embedding=[0.0] * 1536,
                embedding_model="fake-hashing-v1",
            )
        )

        summary = DocumentSummary(
            user_id=user.id,
            document_id=document.id,
            summary_type="brief",
            status=status,
            content=None,
        )
        session.add(summary)
        await session.commit()
        return user.id, document.id, summary.id


async def _cleanup(user_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(
            delete(DocumentSummary).where(DocumentSummary.user_id == user_id)
        )
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.user_id == user_id)
        )
        await session.execute(delete(Document).where(Document.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _fetch_summary(
    user_id: uuid.UUID, summary_id: uuid.UUID
) -> DocumentSummary | None:
    async with async_session_factory() as session:
        return await DocumentSummaryRepository(session).get(user_id, summary_id)


def test_run_summary_job_completes_the_full_pipeline(monkeypatch):
    scripted_llm = FakeLLMProvider(
        responses=["A concise summary."],
        structured_responses=[QualityCheckResult(passed=True)],
    )
    monkeypatch.setattr(summary_worker, "get_llm_provider", lambda: scripted_llm)

    user_id, _document_id, summary_id = _run(_create_user_document_and_summary())
    try:
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_summary_job(str(user_id), str(summary_id))

        summary = _run(_fetch_summary(user_id, summary_id))
        assert summary.status == "completed"
        assert summary.content == "A concise summary."
    finally:
        _run(_cleanup(user_id))


def test_run_summary_job_unexpected_error_propagates_and_does_not_mark_failed(
    monkeypatch,
):
    class _BrokenLLMProvider(FakeLLMProvider):
        async def generate(self, *args, **kwargs):
            raise RuntimeError("provider connection reset")

    monkeypatch.setattr(
        summary_worker, "get_llm_provider", lambda: _BrokenLLMProvider()
    )

    user_id, _document_id, summary_id = _run(_create_user_document_and_summary())
    try:
        try:
            with _dispose_engine_before_and_after_sync_entrypoint_call():
                run_summary_job(str(user_id), str(summary_id))
            raise AssertionError("expected run_summary_job to raise")
        except RuntimeError:
            pass

        summary = _run(_fetch_summary(user_id, summary_id))
        assert summary.status == "processing"  # untouched by this attempt alone
    finally:
        _run(_cleanup(user_id))


def test_on_summary_failure_is_a_noop_while_retries_remain():
    from types import SimpleNamespace

    job = SimpleNamespace(should_retry=True, args=("ignored", "ignored"))
    on_summary_failure(job, None, None, None, None)  # must not touch any row


def test_on_summary_failure_marks_summary_failed_once_retries_are_exhausted():
    from types import SimpleNamespace

    user_id, _document_id, summary_id = _run(_create_user_document_and_summary())
    try:
        job = SimpleNamespace(should_retry=False, args=(str(user_id), str(summary_id)))
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            on_summary_failure(job, None, None, None, None)

        summary = _run(_fetch_summary(user_id, summary_id))
        assert summary.status == "failed"
        assert summary.content is None
    finally:
        _run(_cleanup(user_id))


def test_run_summary_job_never_touches_another_users_summary(monkeypatch):
    """Cross-tenant category (testing.md §3.5) applied to the worker
    entrypoint itself: a stray job carrying a mismatched user_id/summary_id
    pair must be a silent no-op."""
    scripted_llm = FakeLLMProvider(
        responses=["changed"],
        structured_responses=[QualityCheckResult(passed=True)],
    )
    monkeypatch.setattr(summary_worker, "get_llm_provider", lambda: scripted_llm)

    owner_id, _document_id, summary_id = _run(_create_user_document_and_summary())
    try:
        attacker_id = uuid.uuid4()
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_summary_job(str(attacker_id), str(summary_id))

        summary = _run(_fetch_summary(owner_id, summary_id))
        assert summary.status == "processing"  # untouched by the wrong-tenant call
    finally:
        _run(_cleanup(owner_id))

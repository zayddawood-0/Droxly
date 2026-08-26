"""
tasks/remediation-plan.md R6 — workers/comparison_worker.py. Mirrors
test_extraction_worker.py's shape exactly: real Postgres, real (committed)
rows, the real sync RQ entrypoint (`asyncio.run` internally), so this file
uses the same plain-sync-`def`-test / real-commit convention, not the
`db_session` SAVEPOINT fixture.
"""

import asyncio
import uuid

from sqlalchemy import delete

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.graphs.comparison import ClassifiedDifferences
from app.ai.llm import FakeLLMProvider
from app.core.database import async_session_factory, engine
from app.models import Comparison, Document, DocumentChunk, User
from app.repositories.comparison_repository import ComparisonRepository
from app.workers import comparison_worker
from app.workers.comparison_worker import on_comparison_failure, run_comparison_job


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


async def _create_user_documents_and_comparison(*, status: str = "processing"):
    async with async_session_factory() as session:
        user = User(
            email=f"{uuid.uuid4()}@example.com",
            display_name="Comparison Worker Test User",
            password_hash="not-a-real-hash",
        )
        session.add(user)
        await session.flush()

        embedding_provider = FakeEmbeddingProvider()
        document_ids = []
        for content in (
            "The invoice total is $100.",
            "The invoice total is $150.",
        ):
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
            [vector] = await embedding_provider.embed_batch([content])
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
                    embedding=vector,
                    embedding_model=embedding_provider.model_name,
                )
            )
            document_ids.append(document.id)

        comparison = Comparison(
            user_id=user.id,
            document_a_id=document_ids[0],
            document_b_id=document_ids[1],
            result_json={},
            status=status,
        )
        session.add(comparison)
        await session.commit()
        return user.id, document_ids, comparison.id


async def _cleanup(user_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(delete(Comparison).where(Comparison.user_id == user_id))
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.user_id == user_id)
        )
        await session.execute(delete(Document).where(Document.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _fetch_comparison(
    user_id: uuid.UUID, comparison_id: uuid.UUID
) -> Comparison | None:
    async with async_session_factory() as session:
        return await ComparisonRepository(session).get(user_id, comparison_id)


def test_run_comparison_job_completes_the_full_pipeline(monkeypatch):
    scripted_llm = FakeLLMProvider(
        responses=["The total changed from $100 to $150."],
        structured_responses=[ClassifiedDifferences(categories=["numeric"])],
    )
    monkeypatch.setattr(comparison_worker, "get_llm_provider", lambda: scripted_llm)

    user_id, _document_ids, comparison_id = _run(
        _create_user_documents_and_comparison()
    )
    try:
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_comparison_job(str(user_id), str(comparison_id))

        comparison = _run(_fetch_comparison(user_id, comparison_id))
        assert comparison.status == "completed"
        assert comparison.result_json["modifications"][0]["change_type"] == "numeric"
    finally:
        _run(_cleanup(user_id))


def test_run_comparison_job_unexpected_error_propagates_and_does_not_mark_failed(
    monkeypatch,
):
    class _BrokenLLMProvider(FakeLLMProvider):
        async def generate(self, *args, **kwargs):
            raise RuntimeError("provider connection reset")

    monkeypatch.setattr(
        comparison_worker, "get_llm_provider", lambda: _BrokenLLMProvider()
    )

    user_id, _document_ids, comparison_id = _run(
        _create_user_documents_and_comparison()
    )
    try:
        try:
            with _dispose_engine_before_and_after_sync_entrypoint_call():
                run_comparison_job(str(user_id), str(comparison_id))
            raise AssertionError("expected run_comparison_job to raise")
        except RuntimeError:
            pass

        comparison = _run(_fetch_comparison(user_id, comparison_id))
        assert comparison.status == "processing"  # untouched by this attempt alone
    finally:
        _run(_cleanup(user_id))


def test_on_comparison_failure_is_a_noop_while_retries_remain():
    from types import SimpleNamespace

    job = SimpleNamespace(should_retry=True, args=("ignored", "ignored"))
    on_comparison_failure(job, None, None, None, None)  # must not touch any row


def test_on_comparison_failure_marks_comparison_failed_once_retries_are_exhausted():
    from types import SimpleNamespace

    user_id, _document_ids, comparison_id = _run(
        _create_user_documents_and_comparison()
    )
    try:
        job = SimpleNamespace(
            should_retry=False, args=(str(user_id), str(comparison_id))
        )
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            on_comparison_failure(job, None, None, None, None)

        comparison = _run(_fetch_comparison(user_id, comparison_id))
        assert comparison.status == "failed"
        assert comparison.result_json["additions"] == []
    finally:
        _run(_cleanup(user_id))


def test_run_comparison_job_never_touches_another_users_comparison(monkeypatch):
    """Cross-tenant category (testing.md §3.5) applied to the worker
    entrypoint itself: a stray job carrying a mismatched user_id/
    comparison_id pair must be a silent no-op."""
    scripted_llm = FakeLLMProvider(
        responses=["changed"],
        structured_responses=[ClassifiedDifferences(categories=["numeric"])],
    )
    monkeypatch.setattr(comparison_worker, "get_llm_provider", lambda: scripted_llm)

    owner_id, _document_ids, comparison_id = _run(
        _create_user_documents_and_comparison()
    )
    try:
        attacker_id = uuid.uuid4()
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_comparison_job(str(attacker_id), str(comparison_id))

        comparison = _run(_fetch_comparison(owner_id, comparison_id))
        assert comparison.status == "processing"  # untouched by the wrong-tenant call
    finally:
        _run(_cleanup(owner_id))

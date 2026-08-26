"""
tasks/remediation-plan.md R7 — SummaryProcessingService, the worker-invoked
half of summarization (mirrors test_comparison_processing_service.py's
shape: real Postgres via `db_session`, real chunk repository, and a
scripted FakeLLMProvider — no RQ/queue involved, this exercises the
graph-running orchestration directly).
"""

import uuid

from sqlalchemy import select

from app.ai.graphs.summarization import QualityCheckResult
from app.ai.llm import FakeLLMProvider
from app.document_processing.chunking import chunk_text
from app.models import Document, DocumentChunk
from app.models.observability import AiRequest
from app.repositories.document_repository import DocumentChunkRepository
from app.repositories.observability_repository import AiRequestRepository
from app.repositories.summary_repository import DocumentSummaryRepository
from app.services.summary_processing_service import SummaryProcessingService
from tests.conftest import make_user


async def _make_ready_document(db_session, user_id, *, contents: list[str]) -> Document:
    document = Document(
        user_id=user_id,
        file_name="doc.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="ready",
    )
    db_session.add(document)
    await db_session.flush()
    for i, content in enumerate(contents):
        db_session.add(
            DocumentChunk(
                user_id=user_id,
                document_id=document.id,
                chunk_index=i,
                content=content,
                page_number=i + 1,
                char_start=0,
                char_end=len(content),
                token_count=len(content.split()),
                embedding=[0.0] * 1536,
                embedding_model="fake-hashing-v1",
            )
        )
    await db_session.flush()
    return document


def _build_service(db_session, llm: FakeLLMProvider) -> SummaryProcessingService:
    return SummaryProcessingService(
        DocumentSummaryRepository(db_session),
        DocumentChunkRepository(db_session),
        AiRequestRepository(db_session),
        llm,
    )


async def _ai_requests_for(db_session, user_id, operation=None) -> list[AiRequest]:
    stmt = select(AiRequest).where(AiRequest.user_id == user_id)
    if operation is not None:
        stmt = stmt.where(AiRequest.operation == operation)
    return list((await db_session.execute(stmt)).scalars().all())


async def test_successful_single_pass_summary_is_persisted(db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(
        db_session, user.id, contents=["A modest document about quarterly performance."]
    )
    summary = await DocumentSummaryRepository(db_session).create(
        user.id,
        document_id=document.id,
        summary_type="brief",
        status="processing",
        content=None,
    )
    llm = FakeLLMProvider(
        responses=["A concise summary of the quarter."],
        structured_responses=[QualityCheckResult(passed=True)],
    )
    service = _build_service(db_session, llm)

    await service.run_summary(user.id, summary.id)

    updated = await DocumentSummaryRepository(db_session).get(user.id, summary.id)
    assert updated.status == "completed"
    assert updated.content == "A concise summary of the quarter."

    comparison_rows = await _ai_requests_for(db_session, user.id, "summarization")
    assert (
        len(comparison_rows) == 2
    )  # 1 generate() (single-pass) + 1 generate_structured()
    assert all(row.status == "success" for row in comparison_rows)
    assert all(
        row.input_tokens is not None and row.input_tokens > 0 for row in comparison_rows
    )


async def test_map_reduce_strategy_logs_one_row_per_chunk_call_plus_combine(db_session):
    """A document large enough to trigger map_reduce makes one real
    generate() call per chunk plus one final combine call — every one of
    them must get its own ai_requests row, never collapsed into one."""
    user = await make_user(db_session)
    long_content = (
        "This document discusses quarterly revenue growth in great detail. " * 400
    )
    document = await _make_ready_document(db_session, user.id, contents=[long_content])
    summary = await DocumentSummaryRepository(db_session).create(
        user.id,
        document_id=document.id,
        summary_type="detailed",
        status="processing",
        content=None,
    )
    # Precompute exactly how many chunks chunk_text() produces for this
    # document so the queued "combined summary" response lands on the real
    # combine call (the one immediately after all per-chunk calls), not an
    # arbitrary leftover "partial" entry.
    expected_chunk_count = len(chunk_text(long_content))
    llm = FakeLLMProvider(
        responses=["partial"] * expected_chunk_count + ["combined summary"],
        structured_responses=[QualityCheckResult(passed=True)],
    )
    service = _build_service(db_session, llm)

    await service.run_summary(user.id, summary.id)

    updated = await DocumentSummaryRepository(db_session).get(user.id, summary.id)
    assert updated.status == "completed"
    assert updated.content == "combined summary"

    rows = await _ai_requests_for(db_session, user.id, "summarization")
    # expected_chunk_count generate() calls (one per chunk) + 1 combine
    # generate() call + 1 generate_structured() quality check — never a
    # single collapsed row regardless of how many real calls happened.
    assert len(rows) == expected_chunk_count + 2
    assert all(row.status == "success" for row in rows)
    assert all(row.input_tokens is not None and row.input_tokens > 0 for row in rows)
    # Real token counts vary per call (different chunk sizes) — proof
    # they're not a single duplicated/conflated value.
    assert len({row.input_tokens for row in rows}) > 1


async def test_bullet_points_summary_type_is_accepted_end_to_end(db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(
        db_session, user.id, contents=["Point one. Point two. Point three."]
    )
    summary = await DocumentSummaryRepository(db_session).create(
        user.id,
        document_id=document.id,
        summary_type="bullet_points",
        status="processing",
        content=None,
    )
    llm = FakeLLMProvider(
        responses=["- Point one\n- Point two\n- Point three"],
        structured_responses=[QualityCheckResult(passed=True)],
    )
    service = _build_service(db_session, llm)

    await service.run_summary(user.id, summary.id)

    updated = await DocumentSummaryRepository(db_session).get(user.id, summary.id)
    assert updated.status == "completed"
    assert updated.content == "- Point one\n- Point two\n- Point three"


async def test_quality_check_retry_then_pass_logs_every_call_separately(db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(
        db_session, user.id, contents=["Some real document content."]
    )
    summary = await DocumentSummaryRepository(db_session).create(
        user.id,
        document_id=document.id,
        summary_type="brief",
        status="processing",
        content=None,
    )
    llm = FakeLLMProvider(
        responses=["attempt 1", "attempt 2"],
        structured_responses=[
            QualityCheckResult(passed=False, feedback="too vague"),
            QualityCheckResult(passed=True),
        ],
    )
    service = _build_service(db_session, llm)

    await service.run_summary(user.id, summary.id)

    updated = await DocumentSummaryRepository(db_session).get(user.id, summary.id)
    assert updated.status == "completed"
    assert updated.content == "attempt 2"

    rows = await _ai_requests_for(db_session, user.id, "summarization")
    # 2 generate() (one per attempt) + 2 generate_structured() (one per
    # quality check) — every real call gets its own row, never collapsed.
    assert len(rows) == 4
    assert all(row.status == "success" for row in rows)


async def test_quality_check_retry_exhaustion_persists_failed_status(db_session):
    """langgraph.md §3 — exceeding the retry budget (3 total attempts)
    routes to terminal failure; the persisted row must reflect that, not
    loop or silently succeed with a low-quality draft."""
    user = await make_user(db_session)
    document = await _make_ready_document(
        db_session, user.id, contents=["Some real document content."]
    )
    summary = await DocumentSummaryRepository(db_session).create(
        user.id,
        document_id=document.id,
        summary_type="brief",
        status="processing",
        content=None,
    )
    llm = FakeLLMProvider(
        responses=["a1", "a2", "a3"],
        structured_responses=[
            QualityCheckResult(passed=False, feedback="bad"),
            QualityCheckResult(passed=False, feedback="bad"),
            QualityCheckResult(passed=False, feedback="still bad"),
        ],
    )
    service = _build_service(db_session, llm)

    await service.run_summary(user.id, summary.id)

    updated = await DocumentSummaryRepository(db_session).get(user.id, summary.id)
    assert updated.status == "failed"
    assert updated.content is None

    rows = await _ai_requests_for(db_session, user.id, "summarization")
    assert len(rows) == 6  # 3 generate() + 3 generate_structured()


async def test_missing_summary_is_silently_skipped(db_session):
    user = await make_user(db_session)
    llm = FakeLLMProvider()
    service = _build_service(db_session, llm)

    await service.run_summary(user.id, uuid.uuid4())  # must not raise

    assert await _ai_requests_for(db_session, user.id) == []


async def test_already_terminal_summary_is_a_no_op(db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id, contents=["content"])
    summary = await DocumentSummaryRepository(db_session).create(
        user.id,
        document_id=document.id,
        summary_type="brief",
        status="completed",
        content="already done",
    )
    llm = FakeLLMProvider()  # would raise if actually invoked
    service = _build_service(db_session, llm)

    await service.run_summary(user.id, summary.id)  # must not raise

    unchanged = await DocumentSummaryRepository(db_session).get(user.id, summary.id)
    assert unchanged.status == "completed"
    assert unchanged.content == "already done"


async def test_ai_request_logging_failure_does_not_affect_summary_outcome(db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(
        db_session, user.id, contents=["Some real document content."]
    )
    summary = await DocumentSummaryRepository(db_session).create(
        user.id,
        document_id=document.id,
        summary_type="brief",
        status="processing",
        content=None,
    )
    llm = FakeLLMProvider(
        responses=["A concise summary."],
        structured_responses=[QualityCheckResult(passed=True)],
    )

    class _FailingAiRequestRepository(AiRequestRepository):
        async def create(self, user_id, **fields):
            raise RuntimeError("observability store unavailable")

    service = SummaryProcessingService(
        DocumentSummaryRepository(db_session),
        DocumentChunkRepository(db_session),
        _FailingAiRequestRepository(db_session),
        llm,
    )

    await service.run_summary(user.id, summary.id)  # must not raise

    updated = await DocumentSummaryRepository(db_session).get(user.id, summary.id)
    assert updated.status == "completed"
    assert updated.content == "A concise summary."

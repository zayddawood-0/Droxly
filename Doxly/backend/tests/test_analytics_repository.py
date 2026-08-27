"""
api.md §9 (/analytics) — tasks/remediation-plan.md R9. Repository-level
coverage of AnalyticsRepository's aggregate queries, independent of the
HTTP layer (test_analytics_api.py covers the full request/response
contract, including the dedicated cross-tenant suite remediation-plan.md
§12.1 requires).
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Document, User
from app.repositories.analytics_repository import AnalyticsRepository
from app.repositories.observability_repository import AiRequestRepository


async def _make_user(session) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Test User",
        password_hash="not-a-real-hash",
    )
    session.add(user)
    await session.flush()
    return user


async def _make_document(
    session, user_id, *, status: str = "ready", created_at=None
) -> Document:
    document = Document(
        user_id=user_id,
        file_name="report.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        status=status,
    )
    session.add(document)
    await session.flush()
    if created_at is not None:
        document.created_at = created_at
        await session.flush()
    return document


async def _make_ai_request(session, user_id, *, operation: str, created_at=None):
    request = await AiRequestRepository(session).create(
        user_id,
        operation=operation,
        provider="fake",
        model="fake-model",
        input_tokens=10,
        output_tokens=None,
        latency_ms=5,
        status="success",
        error_code=None,
    )
    if created_at is not None:
        request.created_at = created_at
        await session.flush()
    return request


def _repo(session) -> AnalyticsRepository:
    return AnalyticsRepository(session)


async def test_documents_processed_by_day_only_counts_ready_documents(db_session):
    user = await _make_user(db_session)
    await _make_document(db_session, user.id, status="ready")
    await _make_document(db_session, user.id, status="queued")
    await _make_document(db_session, user.id, status="failed")

    counts = await _repo(db_session).documents_processed_by_day(
        user.id, datetime.now(UTC) - timedelta(days=1)
    )

    assert sum(c.count for c in counts) == 1


async def test_documents_processed_by_day_excludes_soft_deleted(db_session):
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user.id, status="ready")
    doc.deleted_at = datetime.now(UTC)
    await db_session.flush()

    counts = await _repo(db_session).documents_processed_by_day(
        user.id, datetime.now(UTC) - timedelta(days=1)
    )

    assert sum(c.count for c in counts) == 0


async def test_documents_processed_by_day_excludes_documents_outside_the_window(
    db_session,
):
    user = await _make_user(db_session)
    await _make_document(
        db_session,
        user.id,
        status="ready",
        created_at=datetime.now(UTC) - timedelta(days=40),
    )

    counts = await _repo(db_session).documents_processed_by_day(
        user.id, datetime.now(UTC) - timedelta(days=7)
    )

    assert sum(c.count for c in counts) == 0


async def test_documents_processed_by_day_is_scoped_to_the_user(db_session):
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    await _make_document(db_session, other.id, status="ready")

    counts = await _repo(db_session).documents_processed_by_day(
        owner.id, datetime.now(UTC) - timedelta(days=1)
    )

    assert sum(c.count for c in counts) == 0


async def test_ai_requests_by_day_groups_same_day_calls_together(db_session):
    user = await _make_user(db_session)
    now = datetime.now(UTC)
    await _make_ai_request(db_session, user.id, operation="chat", created_at=now)
    await _make_ai_request(db_session, user.id, operation="extraction", created_at=now)
    await _make_ai_request(
        db_session, user.id, operation="chat", created_at=now - timedelta(days=2)
    )

    counts = await _repo(db_session).ai_requests_by_day(
        user.id, now - timedelta(days=7)
    )

    assert sum(c.count for c in counts) == 3
    today_count = next(c for c in counts if c.day == now.date())
    assert today_count.count == 2


async def test_ai_requests_by_day_is_scoped_to_the_user(db_session):
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    await _make_ai_request(db_session, other.id, operation="chat")

    counts = await _repo(db_session).ai_requests_by_day(
        owner.id, datetime.now(UTC) - timedelta(days=1)
    )

    assert sum(c.count for c in counts) == 0


async def test_most_used_features_excludes_embedding_operation(db_session):
    user = await _make_user(db_session)
    await _make_ai_request(db_session, user.id, operation="chat")
    await _make_ai_request(db_session, user.id, operation="chat")
    await _make_ai_request(db_session, user.id, operation="embedding")

    features = await _repo(db_session).most_used_features(
        user.id, datetime.now(UTC) - timedelta(days=1)
    )

    feature_names = {f.feature for f in features}
    assert "embedding" not in feature_names
    assert {f.feature: f.count for f in features}["chat"] == 2


async def test_most_used_features_orders_by_count_descending(db_session):
    user = await _make_user(db_session)
    await _make_ai_request(db_session, user.id, operation="summarization")
    await _make_ai_request(db_session, user.id, operation="extraction")
    await _make_ai_request(db_session, user.id, operation="extraction")
    await _make_ai_request(db_session, user.id, operation="extraction")

    features = await _repo(db_session).most_used_features(
        user.id, datetime.now(UTC) - timedelta(days=1)
    )

    assert features[0].feature == "extraction"
    assert features[0].count == 3


async def test_most_used_features_is_scoped_to_the_user(db_session):
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    await _make_ai_request(db_session, other.id, operation="chat")

    features = await _repo(db_session).most_used_features(
        owner.id, datetime.now(UTC) - timedelta(days=1)
    )

    assert features == []

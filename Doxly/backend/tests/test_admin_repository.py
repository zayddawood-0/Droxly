"""
api.md §12 (/admin) — tasks/remediation-plan.md R10. Repository-level
coverage: UserRepository.list_paginated (admin's cross-user listing, the
one deliberate exception to the tenant-scoping rule) and AdminRepository's
system-health aggregates.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.models import Document, User
from app.repositories.admin_repository import AdminRepository
from app.repositories.observability_repository import AiRequestRepository
from app.repositories.user_repository import UserRepository


async def _make_user(session, *, status: str = "active", plan: str = "free") -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Test User",
        password_hash="not-a-real-hash",
        status=status,
        plan=plan,
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


async def _make_ai_request(
    session, user_id, *, status: str = "success", created_at=None
):
    request = await AiRequestRepository(session).create(
        user_id,
        operation="chat",
        provider="fake",
        model="fake-model",
        input_tokens=10,
        output_tokens=5,
        latency_ms=5,
        status=status,
        error_code="generation_failed" if status != "success" else None,
    )
    if created_at is not None:
        request.created_at = created_at
        await session.flush()
    return request


# --- UserRepository.list_paginated (admin's deliberate cross-user listing) ---


async def test_list_paginated_returns_users_across_the_whole_base(db_session):
    await _make_user(db_session)
    await _make_user(db_session)

    users, total = await UserRepository(db_session).list_paginated(limit=20, offset=0)

    assert total >= 2
    assert len(users) >= 2


async def test_list_paginated_filters_by_status(db_session):
    active = await _make_user(db_session, status="active")
    suspended = await _make_user(db_session, status="suspended")

    users, _total = await UserRepository(db_session).list_paginated(
        limit=20, offset=0, status="suspended"
    )

    ids = {u.id for u in users}
    assert suspended.id in ids
    assert active.id not in ids


async def test_list_paginated_filters_by_plan(db_session):
    free = await _make_user(db_session, plan="free")
    pro = await _make_user(db_session, plan="pro")

    users, _total = await UserRepository(db_session).list_paginated(
        limit=20, offset=0, plan="pro"
    )

    ids = {u.id for u in users}
    assert pro.id in ids
    assert free.id not in ids


# --- AdminRepository system-health aggregates ---


async def test_processing_failure_rate_24h_computes_the_ratio(db_session):
    user = await _make_user(db_session)
    await _make_document(db_session, user.id, status="ready")
    await _make_document(db_session, user.id, status="ready")
    await _make_document(db_session, user.id, status="failed")

    rate = await AdminRepository(db_session).processing_failure_rate_24h()

    assert rate > 0.0


async def test_processing_failure_rate_24h_excludes_documents_outside_the_window(
    db_session,
):
    user = await _make_user(db_session)
    await _make_document(
        db_session,
        user.id,
        status="failed",
        created_at=datetime.now(UTC) - timedelta(hours=48),
    )

    rate_before = await AdminRepository(db_session).processing_failure_rate_24h()
    await _make_document(db_session, user.id, status="ready")
    rate_after = await AdminRepository(db_session).processing_failure_rate_24h()

    # The 48h-old failed document never enters either window's denominator.
    assert rate_after <= rate_before or rate_after == 0.0


async def test_processing_failure_rate_24h_is_zero_with_no_documents(db_session):
    rate = await AdminRepository(db_session).processing_failure_rate_24h()
    assert rate == 0.0


async def test_ai_requests_24h_counts_across_every_user(db_session):
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    await _make_ai_request(db_session, user_a.id)
    await _make_ai_request(db_session, user_b.id)

    count = await AdminRepository(db_session).ai_requests_24h()

    assert count >= 2


async def test_ai_error_rate_24h_computes_the_ratio(db_session):
    user = await _make_user(db_session)
    await _make_ai_request(db_session, user.id, status="success")
    await _make_ai_request(db_session, user.id, status="error")

    rate = await AdminRepository(db_session).ai_error_rate_24h()

    assert 0.0 < rate < 1.0


async def test_ai_error_rate_24h_is_zero_with_no_requests(db_session):
    rate = await AdminRepository(db_session).ai_error_rate_24h()
    assert rate == 0.0

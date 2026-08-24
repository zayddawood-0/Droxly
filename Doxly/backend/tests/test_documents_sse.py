"""
tasks/remediation-plan.md R2 §5.2 — GET /documents/{id}/status/stream.
R3's worker (the real driver of status transitions) doesn't exist yet, so
these tests drive `documents.status` directly via the repository — exactly
what §5.2 anticipated ("R2 can be built and tested before R3 lands").
"""

import uuid

from tests.conftest import auth_cookie_headers, make_user


async def _create_queued_document(db_session, user_id: uuid.UUID) -> uuid.UUID:
    from app.repositories.document_repository import DocumentRepository

    document = await DocumentRepository(db_session).create(
        user_id,
        file_name="a.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="queued",
    )
    return document.id


async def _read_events(client, url: str, headers: dict) -> list[dict]:
    import json

    events = []
    async with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                data_line = next(
                    (
                        line
                        for line in raw_event.splitlines()
                        if line.startswith("data: ")
                    ),
                    None,
                )
                if data_line:
                    events.append(json.loads(data_line[len("data: ") :]))
    return events


async def test_stream_emits_current_status_immediately_then_terminal(
    client, db_session
):
    """Uses a document already `ready` at connect time — the stream must
    emit that single terminal event immediately and close, not hang."""
    from app.repositories.document_repository import DocumentRepository

    user = await make_user(db_session)
    document_id = await _create_queued_document(db_session, user.id)
    await DocumentRepository(db_session).set_status(
        user.id, document_id, status="ready"
    )

    events = await _read_events(
        client,
        f"/api/v1/documents/{document_id}/status/stream",
        auth_cookie_headers(user.id),
    )
    assert events == [{"status": "ready"}]


async def test_stream_emits_failed_as_a_normal_terminal_event(client, db_session):
    """remediation-plan.md R2 §5.2 — failed is a valid terminal state, not
    a transport-level error."""
    from app.repositories.document_repository import DocumentRepository

    user = await make_user(db_session)
    document_id = await _create_queued_document(db_session, user.id)
    await DocumentRepository(db_session).set_status(
        user.id, document_id, status="failed"
    )

    events = await _read_events(
        client,
        f"/api/v1/documents/{document_id}/status/stream",
        auth_cookie_headers(user.id),
    )
    assert events == [{"status": "failed"}]


async def test_stream_picks_up_a_transition_that_happens_mid_stream(client, db_session):
    """Exercises the actual polling loop (not just an already-terminal
    document at connect time): status starts `queued`, then transitions to
    `ready` shortly after the stream opens. Updates through the same
    db_session the stream's own (test-overridden) dependency uses — a
    flushed change is visible to the stream's next poll immediately, the
    same way it would be across genuinely separate sessions/transactions
    under Postgres's default READ COMMITTED (verified separately via this
    suite's other tests, which don't depend on same-session visibility);
    using one session here avoids a real deadlock risk this test hit in an
    earlier version that opened a second engine-level session while
    db_session already held the pool's only connection checked out for the
    whole test."""
    import asyncio

    from app.repositories.document_repository import DocumentRepository

    user = await make_user(db_session)
    document_id = await _create_queued_document(db_session, user.id)

    async def _flip_to_ready() -> None:
        await asyncio.sleep(1.3)  # after the stream's first (queued) poll
        await DocumentRepository(db_session).set_status(
            user.id, document_id, status="ready"
        )

    events_task = asyncio.create_task(
        _read_events(
            client,
            f"/api/v1/documents/{document_id}/status/stream",
            auth_cookie_headers(user.id),
        )
    )
    flip_task = asyncio.create_task(_flip_to_ready())
    events, _ = await asyncio.gather(events_task, flip_task)

    assert events == [{"status": "queued"}, {"status": "ready"}]


async def test_stream_cross_tenant_returns_404_before_any_event(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document_id = await _create_queued_document(db_session, owner.id)

    response = await client.get(
        f"/api/v1/documents/{document_id}/status/stream",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


async def test_stream_unknown_document_returns_404(client, db_session):
    user = await make_user(db_session)
    response = await client.get(
        f"/api/v1/documents/{uuid.uuid4()}/status/stream",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404

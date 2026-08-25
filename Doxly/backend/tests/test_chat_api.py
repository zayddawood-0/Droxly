"""
tasks/remediation-plan.md R4 — testing.md §3.3 API tests + §3.5 cross-tenant
tests for FR-AI-001..003 (conversation CRUD, excluding the streaming
message endpoints — see test_chat_sse.py).
"""

import uuid

from tests.conftest import auth_cookie_headers, make_user


async def _make_ready_document(db_session, user_id, *, file_name="report.pdf"):
    from app.models import Document

    document = Document(
        user_id=user_id,
        file_name=file_name,
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="ready",
    )
    db_session.add(document)
    await db_session.flush()
    return document


async def test_create_workspace_conversation(client, db_session):
    user = await make_user(db_session)
    response = await client.post(
        "/api/v1/chat/conversations",
        json={},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scope_type"] == "workspace"
    assert body["document_ids"] == []
    assert body["title"] is None
    assert "id" in body and "created_at" in body


async def test_create_single_document_conversation(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    response = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(document.id)]},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scope_type"] == "single_document"
    assert body["document_ids"] == [str(document.id)]


async def test_create_multi_document_conversation(client, db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, user.id, file_name="a.pdf")
    doc_b = await _make_ready_document(db_session, user.id, file_name="b.pdf")

    response = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(doc_a.id), str(doc_b.id)]},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 201, response.text
    assert response.json()["scope_type"] == "multi_document"


async def test_create_conversation_with_unowned_document_returns_404(
    client, db_session
):
    owner = await make_user(db_session)
    other = await make_user(db_session)
    document = await _make_ready_document(db_session, other.id)

    response = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(document.id)]},
        headers=auth_cookie_headers(owner.id),
    )
    assert response.status_code == 404


async def test_create_conversation_with_not_ready_document_returns_409(
    client, db_session
):
    from app.models import Document

    user = await make_user(db_session)
    document = Document(
        user_id=user.id,
        file_name="processing.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="extracting",
    )
    db_session.add(document)
    await db_session.flush()

    response = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(document.id)]},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_list_conversations_sorted_by_updated_at_desc(client, db_session):
    """
    Both conversations are created inside this test's single shared,
    uncommitted transaction (tests/conftest.py's SAVEPOINT-isolated
    db_session) — Postgres's `now()` returns the *transaction* start time,
    not wall-clock statement time, so two inserts in the same transaction
    can otherwise tie on `updated_at`. Explicitly setting distinct values
    tests the sort itself, not incidental timestamp-generation timing.
    """
    import datetime

    from app.repositories.conversation_repository import ConversationRepository

    user = await make_user(db_session)
    first = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    second = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )

    repo = ConversationRepository(db_session)
    first_conv = await repo.get(user.id, uuid.UUID(first.json()["id"]))
    second_conv = await repo.get(user.id, uuid.UUID(second.json()["id"]))
    now = datetime.datetime.now(datetime.UTC)
    first_conv.updated_at = now - datetime.timedelta(seconds=10)
    second_conv.updated_at = now
    await db_session.flush()

    response = await client.get(
        "/api/v1/chat/conversations", headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    ids = [item["id"] for item in body["items"]]
    assert ids == [second.json()["id"], first.json()["id"]]


async def test_list_conversations_never_includes_another_users_rows(client, db_session):
    owner = await make_user(db_session)
    other = await make_user(db_session)
    await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(other.id)
    )

    response = await client.get(
        "/api/v1/chat/conversations", headers=auth_cookie_headers(owner.id)
    )
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


async def test_get_conversation_detail_returns_ordered_messages(client, db_session):
    from app.repositories.conversation_repository import (
        ConversationRepository,
        MessageRepository,
    )

    user = await make_user(db_session)
    conversation = await ConversationRepository(db_session).create(
        user.id, scope_type="workspace", title=None
    )
    await MessageRepository(db_session).create(
        user.id,
        conversation_id=conversation.id,
        role="user",
        content="first",
        token_count=1,
        status="complete",
    )
    await MessageRepository(db_session).create(
        user.id,
        conversation_id=conversation.id,
        role="assistant",
        content="second",
        token_count=1,
        status="complete",
    )

    response = await client.get(
        f"/api/v1/chat/conversations/{conversation.id}",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [m["content"] for m in body["messages"]] == ["first", "second"]
    assert body["messages"][0]["citations"] == []


async def test_get_conversation_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    created = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(owner.id)
    )
    conversation_id = created.json()["id"]

    response = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


async def test_get_unknown_conversation_returns_404(client, db_session):
    user = await make_user(db_session)
    response = await client.get(
        f"/api/v1/chat/conversations/{uuid.uuid4()}",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404


async def test_delete_conversation_soft_deletes(client, db_session):
    user = await make_user(db_session)
    created = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = created.json()["id"]

    response = await client.delete(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 204

    follow_up = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(user.id),
    )
    assert follow_up.status_code == 404


async def test_delete_conversation_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    created = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(owner.id)
    )
    conversation_id = created.json()["id"]

    response = await client.delete(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


async def test_unauthenticated_request_returns_401(client, db_session):
    response = await client.get("/api/v1/chat/conversations")
    assert response.status_code == 401

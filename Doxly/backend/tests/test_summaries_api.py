"""
api.md §5 (/summaries) — tasks/remediation-plan.md R7. Full HTTP-layer
contract tests: exact request/response shapes and error envelopes, auth,
tenant isolation, and document-state preconditions. The summarization
*run* itself is covered by test_summary_processing_service.py and
test_summary_worker.py — every summary here is created and then directly
persisted to its terminal state via the repository.
"""

import uuid

from app.core.queue import get_summary_queue
from app.models import Document
from app.repositories.summary_repository import DocumentSummaryRepository
from tests.conftest import auth_cookie_headers, make_user


async def _make_ready_document(db_session, user_id) -> Document:
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
    return document


async def _make_completed_summary(
    db_session, user_id, document_id, *, summary_type="brief"
):
    return await DocumentSummaryRepository(db_session).create(
        user_id,
        document_id=document_id,
        summary_type=summary_type,
        status="completed",
        content="A concise summary of the document.",
    )


# --- POST /documents/{id}/summaries ---


async def test_create_summary_returns_202_processing(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    response = await client.post(
        f"/api/v1/documents/{document.id}/summaries",
        json={"summary_type": "brief"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "processing"
    assert body["document_id"] == str(document.id)
    assert body["summary_type"] == "brief"
    assert uuid.UUID(body["id"])


async def test_create_summary_enqueues_exactly_one_job(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    queue = get_summary_queue()
    before = queue.count

    response = await client.post(
        f"/api/v1/documents/{document.id}/summaries",
        json={"summary_type": "detailed"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 202
    assert queue.count == before + 1


async def test_create_summary_accepts_bullet_points(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    response = await client.post(
        f"/api/v1/documents/{document.id}/summaries",
        json={"summary_type": "bullet_points"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 202, response.text
    assert response.json()["summary_type"] == "bullet_points"


async def test_create_summary_422s_for_invalid_summary_type(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    response = await client.post(
        f"/api/v1/documents/{document.id}/summaries",
        json={"summary_type": "essay"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_create_summary_404s_for_a_document_that_does_not_exist(
    client, db_session
):
    user = await make_user(db_session)

    response = await client.post(
        f"/api/v1/documents/{uuid.uuid4()}/summaries",
        json={"summary_type": "brief"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_summary_404s_for_another_users_document(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _make_ready_document(db_session, owner.id)

    response = await client.post(
        f"/api/v1/documents/{document.id}/summaries",
        json={"summary_type": "brief"},
        headers=auth_cookie_headers(attacker.id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_summary_409s_when_document_is_not_ready(client, db_session):
    user = await make_user(db_session)
    document = Document(
        user_id=user.id,
        file_name="processing.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="queued",
    )
    db_session.add(document)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/documents/{document.id}/summaries",
        json={"summary_type": "brief"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_create_summary_requires_auth(client, db_session):
    response = await client.post(
        f"/api/v1/documents/{uuid.uuid4()}/summaries",
        json={"summary_type": "brief"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- GET /summaries/{id} ---


async def test_get_summary_returns_the_exact_documented_shape(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    summary = await _make_completed_summary(db_session, user.id, document.id)

    response = await client.get(
        f"/api/v1/summaries/{summary.id}", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(summary.id)
    assert body["document_id"] == str(document.id)
    assert body["summary_type"] == "brief"
    assert body["status"] == "completed"
    assert body["content"] == "A concise summary of the document."
    assert "created_at" in body


async def test_get_summary_content_is_null_while_processing(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    summary = await DocumentSummaryRepository(db_session).create(
        user.id,
        document_id=document.id,
        summary_type="brief",
        status="processing",
        content=None,
    )

    response = await client.get(
        f"/api/v1/summaries/{summary.id}", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["content"] is None


async def test_get_summary_404s_for_missing_or_other_users_summary(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _make_ready_document(db_session, owner.id)
    summary = await _make_completed_summary(db_session, owner.id, document.id)

    missing = await client.get(
        f"/api/v1/summaries/{uuid.uuid4()}", headers=auth_cookie_headers(owner.id)
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    cross_tenant = await client.get(
        f"/api/v1/summaries/{summary.id}", headers=auth_cookie_headers(attacker.id)
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["code"] == "not_found"


# --- GET /documents/{id}/summaries ---


async def test_list_document_summaries_returns_paginated_newest_first(
    client, db_session
):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    first = await _make_completed_summary(
        db_session, user.id, document.id, summary_type="brief"
    )
    second = await _make_completed_summary(
        db_session, user.id, document.id, summary_type="detailed"
    )

    response = await client.get(
        f"/api/v1/documents/{document.id}/summaries",
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0
    ids = {item["id"] for item in body["items"]}
    assert ids == {str(first.id), str(second.id)}
    for item in body["items"]:
        assert set(item.keys()) == {"id", "summary_type", "status", "created_at"}


async def test_regenerating_a_summary_does_not_overwrite_the_prior_one(
    client, db_session
):
    """FR-SUM-002 — a fresh request creates a new row; the prior summary
    remains fully accessible, never overwritten or hidden."""
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    original = await _make_completed_summary(
        db_session, user.id, document.id, summary_type="brief"
    )

    response = await client.post(
        f"/api/v1/documents/{document.id}/summaries",
        json={"summary_type": "detailed"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 202
    new_id = response.json()["id"]

    list_response = await client.get(
        f"/api/v1/documents/{document.id}/summaries",
        headers=auth_cookie_headers(user.id),
    )
    ids = {item["id"] for item in list_response.json()["items"]}
    assert ids == {str(original.id), new_id}

    original_still_readable = await client.get(
        f"/api/v1/summaries/{original.id}", headers=auth_cookie_headers(user.id)
    )
    assert original_still_readable.status_code == 200
    assert (
        original_still_readable.json()["content"]
        == "A concise summary of the document."
    )


async def test_list_document_summaries_404s_for_another_users_document(
    client, db_session
):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _make_ready_document(db_session, owner.id)
    await _make_completed_summary(db_session, owner.id, document.id)

    response = await client.get(
        f"/api/v1/documents/{document.id}/summaries",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

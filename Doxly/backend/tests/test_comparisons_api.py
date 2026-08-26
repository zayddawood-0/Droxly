"""
api.md §7 (/comparisons) — tasks/remediation-plan.md R6. Full HTTP-layer
contract tests: exact request/response shapes and error envelopes, auth,
the two-object tenant-isolation variant remediation-plan.md §9 calls out
explicitly, and document-state preconditions. The comparison *run* itself
is covered by test_comparison_processing_service.py and
test_comparison_worker.py — every comparison here is created and then
directly persisted to its terminal state via the repository.
"""

import uuid

from app.core.queue import get_comparison_queue
from app.models import Document
from app.repositories.comparison_repository import ComparisonRepository
from tests.conftest import auth_cookie_headers, make_user

COMPLETED_RESULT = {
    "alignment_quality": "medium",
    "message": None,
    "additions": [{"document": "b", "page_number": 2, "excerpt": "New section."}],
    "deletions": [],
    "modifications": [
        {
            "change_type": "numeric",
            "a_page_number": 1,
            "a_excerpt": "Total is $100.",
            "b_page_number": 1,
            "b_excerpt": "Total is $150.",
            "explanation": "The total changed from $100 to $150.",
        }
    ],
}


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


async def _make_completed_comparison(db_session, user_id, doc_a_id, doc_b_id):
    return await ComparisonRepository(db_session).create(
        user_id,
        document_a_id=doc_a_id,
        document_b_id=doc_b_id,
        result_json=COMPLETED_RESULT,
        status="completed",
    )


# --- POST /comparisons ---


async def test_create_comparison_returns_202_processing(client, db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, user.id)
    doc_b = await _make_ready_document(db_session, user.id)

    response = await client.post(
        "/api/v1/comparisons",
        json={"document_a_id": str(doc_a.id), "document_b_id": str(doc_b.id)},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "processing"
    assert uuid.UUID(body["id"])


async def test_create_comparison_enqueues_exactly_one_job(client, db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, user.id)
    doc_b = await _make_ready_document(db_session, user.id)
    queue = get_comparison_queue()
    before = queue.count

    response = await client.post(
        "/api/v1/comparisons",
        json={"document_a_id": str(doc_a.id), "document_b_id": str(doc_b.id)},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 202
    assert queue.count == before + 1


async def test_create_comparison_422s_for_identical_documents(client, db_session):
    user = await make_user(db_session)
    doc = await _make_ready_document(db_session, user.id)

    response = await client.post(
        "/api/v1/comparisons",
        json={"document_a_id": str(doc.id), "document_b_id": str(doc.id)},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "identical_documents"


async def test_create_comparison_404s_when_document_a_is_not_owned(client, db_session):
    """Two-object tenant check (remediation-plan.md §9) — a comparison
    naming another user's document as EITHER side must 404, not just when
    the primary document_id is the foreign one."""
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    owners_doc = await _make_ready_document(db_session, owner.id)
    attackers_doc = await _make_ready_document(db_session, attacker.id)

    response = await client.post(
        "/api/v1/comparisons",
        json={
            "document_a_id": str(owners_doc.id),
            "document_b_id": str(attackers_doc.id),
        },
        headers=auth_cookie_headers(attacker.id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_comparison_404s_when_document_b_is_not_owned(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    attackers_doc = await _make_ready_document(db_session, attacker.id)
    owners_doc = await _make_ready_document(db_session, owner.id)

    response = await client.post(
        "/api/v1/comparisons",
        json={
            "document_a_id": str(attackers_doc.id),
            "document_b_id": str(owners_doc.id),
        },
        headers=auth_cookie_headers(attacker.id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_comparison_404s_for_a_document_that_does_not_exist(
    client, db_session
):
    user = await make_user(db_session)
    doc = await _make_ready_document(db_session, user.id)

    response = await client.post(
        "/api/v1/comparisons",
        json={"document_a_id": str(doc.id), "document_b_id": str(uuid.uuid4())},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_comparison_409s_when_either_document_is_not_ready(
    client, db_session
):
    user = await make_user(db_session)
    ready_doc = await _make_ready_document(db_session, user.id)
    not_ready_doc = Document(
        user_id=user.id,
        file_name="processing.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="queued",
    )
    db_session.add(not_ready_doc)
    await db_session.flush()

    response = await client.post(
        "/api/v1/comparisons",
        json={
            "document_a_id": str(ready_doc.id),
            "document_b_id": str(not_ready_doc.id),
        },
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_create_comparison_requires_auth(client, db_session):
    response = await client.post(
        "/api/v1/comparisons",
        json={"document_a_id": str(uuid.uuid4()), "document_b_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# --- GET /comparisons/{id} ---


async def test_get_comparison_returns_the_exact_documented_shape(client, db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, user.id)
    doc_b = await _make_ready_document(db_session, user.id)
    comparison = await _make_completed_comparison(
        db_session, user.id, doc_a.id, doc_b.id
    )

    response = await client.get(
        f"/api/v1/comparisons/{comparison.id}", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(comparison.id)
    assert body["document_a_id"] == str(doc_a.id)
    assert body["document_b_id"] == str(doc_b.id)
    assert body["status"] == "completed"
    assert body["result"]["alignment_quality"] == "medium"
    assert body["result"]["additions"] == [
        {"document": "b", "page_number": 2, "excerpt": "New section."}
    ]
    assert body["result"]["modifications"][0]["change_type"] == "numeric"


async def test_get_comparison_result_is_null_while_processing(client, db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, user.id)
    doc_b = await _make_ready_document(db_session, user.id)
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )

    response = await client.get(
        f"/api/v1/comparisons/{comparison.id}", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["result"] is None


async def test_get_comparison_404s_for_missing_or_other_users_comparison(
    client, db_session
):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, owner.id)
    doc_b = await _make_ready_document(db_session, owner.id)
    comparison = await _make_completed_comparison(
        db_session, owner.id, doc_a.id, doc_b.id
    )

    missing = await client.get(
        f"/api/v1/comparisons/{uuid.uuid4()}", headers=auth_cookie_headers(owner.id)
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    cross_tenant = await client.get(
        f"/api/v1/comparisons/{comparison.id}", headers=auth_cookie_headers(attacker.id)
    )
    assert cross_tenant.status_code == 404
    assert cross_tenant.json()["error"]["code"] == "not_found"


# --- GET /comparisons ---


async def test_list_comparisons_returns_paginated_summaries(client, db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, user.id)
    doc_b = await _make_ready_document(db_session, user.id)
    first = await _make_completed_comparison(db_session, user.id, doc_a.id, doc_b.id)
    second = await _make_completed_comparison(db_session, user.id, doc_a.id, doc_b.id)

    response = await client.get(
        "/api/v1/comparisons", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0
    ids = {item["id"] for item in body["items"]}
    assert ids == {str(first.id), str(second.id)}
    for item in body["items"]:
        assert set(item.keys()) == {
            "id",
            "document_a_id",
            "document_b_id",
            "status",
            "created_at",
        }


async def test_list_comparisons_excludes_other_users_comparisons(client, db_session):
    owner = await make_user(db_session)
    other = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, owner.id)
    doc_b = await _make_ready_document(db_session, owner.id)
    await _make_completed_comparison(db_session, owner.id, doc_a.id, doc_b.id)
    other_doc_a = await _make_ready_document(db_session, other.id)
    other_doc_b = await _make_ready_document(db_session, other.id)
    await _make_completed_comparison(
        db_session, other.id, other_doc_a.id, other_doc_b.id
    )

    response = await client.get(
        "/api/v1/comparisons", headers=auth_cookie_headers(owner.id)
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1

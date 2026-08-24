"""
tasks/remediation-plan.md R2 — testing.md §3.3 API tests + §3.5 cross-tenant
tests for FR-DOC-001..008.
"""

import uuid
from urllib.parse import urlparse

from tests.conftest import auth_cookie_headers, make_user

PDF_BYTES = b"%PDF-1.4\n%fake pdf content for tests\n"
TXT_BYTES = b"hello world, this is plain text content."


def _path_of(url: str) -> str:
    """The presigned URL's host is settings.backend_public_base_url
    (e.g. http://localhost:8000), never the test client's own
    base_url="http://test" — only the path is meaningful for driving the
    SAME app instance via the test transport."""
    parsed = urlparse(url)
    return parsed.path


async def _upload_document(
    client,
    user_id: uuid.UUID,
    *,
    file_name="doc.pdf",
    mime_type="application/pdf",
    data=PDF_BYTES,
) -> dict:
    """Drives the full presign -> PUT -> confirm flow, returning the
    confirmed document's detail response body."""
    presign = await client.post(
        "/api/v1/documents/presign",
        json={"file_name": file_name, "mime_type": mime_type, "size_bytes": len(data)},
        headers=auth_cookie_headers(user_id),
    )
    assert presign.status_code == 201, presign.text
    body = presign.json()
    document_id = body["document_id"]

    put_response = await client.put(_path_of(body["upload_url"]), content=data)
    assert put_response.status_code == 200

    confirm = await client.post(
        f"/api/v1/documents/{document_id}/confirm", headers=auth_cookie_headers(user_id)
    )
    assert confirm.status_code == 202, confirm.text

    detail = await client.get(
        f"/api/v1/documents/{document_id}", headers=auth_cookie_headers(user_id)
    )
    assert detail.status_code == 200
    return detail.json()


# --- FR-DOC-001 upload ---


async def test_presign_creates_queued_document(client, db_session):
    user = await make_user(db_session)
    response = await client.post(
        "/api/v1/documents/presign",
        json={"file_name": "a.pdf", "mime_type": "application/pdf", "size_bytes": 1024},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {
        "document_id",
        "upload_url",
        "upload_method",
        "upload_headers",
        "expires_in",
    }
    assert body["upload_method"] == "PUT"


async def test_presign_unsupported_mime_type_rejected(client, db_session):
    user = await make_user(db_session)
    response = await client.post(
        "/api/v1/documents/presign",
        json={
            "file_name": "a.exe",
            "mime_type": "application/x-msdownload",
            "size_bytes": 10,
        },
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_mime_type"


async def test_presign_over_size_cap_rejected(client, db_session):
    user = await make_user(db_session)
    response = await client.post(
        "/api/v1/documents/presign",
        json={
            "file_name": "huge.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 26 * 1024 * 1024,
        },
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "quota_exceeded"


async def test_presign_over_storage_quota_rejected(client, db_session):
    from app.repositories.user_repository import UserRepository

    user = await make_user(db_session)
    await UserRepository(db_session).update(
        user.id, storage_used_bytes=99 * 1024 * 1024
    )

    response = await client.post(
        "/api/v1/documents/presign",
        json={
            "file_name": "a.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 5 * 1024 * 1024,
        },
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "quota_exceeded"


async def test_presign_over_document_count_quota_rejected(client, db_session):
    from app.repositories.document_repository import DocumentRepository

    user = await make_user(db_session)
    repo = DocumentRepository(db_session)
    for i in range(10):
        await repo.create(
            user.id,
            file_name=f"doc{i}.pdf",
            storage_key=str(uuid.uuid4()),
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="a" * 64,
        )

    response = await client.post(
        "/api/v1/documents/presign",
        json={
            "file_name": "one-too-many.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 100,
        },
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "quota_exceeded"


async def test_full_upload_flow_creates_verified_document(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)

    assert document["status"] == "queued"
    assert document["mime_type"] == "application/pdf"
    assert document["size_bytes"] == len(PDF_BYTES)
    assert len(document["checksum_sha256"]) == 64  # sha256 hex digest


async def test_confirm_increments_storage_used_bytes(client, db_session):
    from app.repositories.user_repository import UserRepository

    user = await make_user(db_session)
    await _upload_document(client, user.id)

    refreshed = await UserRepository(db_session).get_by_id(user.id)
    assert refreshed.storage_used_bytes == len(PDF_BYTES)


async def test_confirm_size_mismatch_rejected(client, db_session):
    user = await make_user(db_session)
    presign = await client.post(
        "/api/v1/documents/presign",
        json={
            "file_name": "a.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 999999,
        },
        headers=auth_cookie_headers(user.id),
    )
    document_id = presign.json()["document_id"]
    upload_url = _path_of(presign.json()["upload_url"])
    await client.put(upload_url, content=PDF_BYTES)  # much smaller than declared 999999

    confirm = await client.post(
        f"/api/v1/documents/{document_id}/confirm", headers=auth_cookie_headers(user.id)
    )
    assert confirm.status_code == 400
    assert confirm.json()["error"]["code"] == "upload_mismatch"


async def test_confirm_magic_byte_mismatch_rejected(client, db_session):
    """security.md §5 — declared PDF, actual content isn't PDF-shaped."""
    user = await make_user(db_session)
    not_a_pdf = b"this is definitely not a pdf file"
    presign = await client.post(
        "/api/v1/documents/presign",
        json={
            "file_name": "fake.pdf",
            "mime_type": "application/pdf",
            "size_bytes": len(not_a_pdf),
        },
        headers=auth_cookie_headers(user.id),
    )
    document_id = presign.json()["document_id"]
    upload_url = _path_of(presign.json()["upload_url"])
    await client.put(upload_url, content=not_a_pdf)

    confirm = await client.post(
        f"/api/v1/documents/{document_id}/confirm", headers=auth_cookie_headers(user.id)
    )
    assert confirm.status_code == 400
    assert confirm.json()["error"]["code"] == "upload_mismatch"


async def test_confirm_without_upload_returns_404(client, db_session):
    user = await make_user(db_session)
    presign = await client.post(
        "/api/v1/documents/presign",
        json={"file_name": "a.pdf", "mime_type": "application/pdf", "size_bytes": 10},
        headers=auth_cookie_headers(user.id),
    )
    document_id = presign.json()["document_id"]

    confirm = await client.post(
        f"/api/v1/documents/{document_id}/confirm", headers=auth_cookie_headers(user.id)
    )
    assert confirm.status_code == 404


async def test_confirm_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    presign = await client.post(
        "/api/v1/documents/presign",
        json={"file_name": "a.pdf", "mime_type": "application/pdf", "size_bytes": 10},
        headers=auth_cookie_headers(owner.id),
    )
    document_id = presign.json()["document_id"]

    response = await client.post(
        f"/api/v1/documents/{document_id}/confirm",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


# --- FR-DOC-002 list ---


async def test_list_documents_returns_only_own_documents(client, db_session):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await _upload_document(client, user_a.id, file_name="a.pdf")
    await _upload_document(client, user_b.id, file_name="b.pdf")

    response = await client.get(
        "/api/v1/documents", headers=auth_cookie_headers(user_a.id)
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1
    assert body["items"][0]["file_name"] == "a.pdf"


async def test_list_documents_filters_by_status(client, db_session):
    from app.repositories.document_repository import DocumentRepository

    user = await make_user(db_session)
    await _upload_document(client, user.id)
    repo = DocumentRepository(db_session)
    await repo.create(
        user.id,
        file_name="failed.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=10,
        checksum_sha256="a" * 64,
        status="failed",
    )

    response = await client.get(
        "/api/v1/documents",
        params={"status": "failed"},
        headers=auth_cookie_headers(user.id),
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "failed"


async def test_list_documents_sorts_by_name(client, db_session):
    user = await make_user(db_session)
    await _upload_document(client, user.id, file_name="zzz.pdf")
    await _upload_document(client, user.id, file_name="aaa.pdf")

    response = await client.get(
        "/api/v1/documents",
        params={"sort": "name_asc"},
        headers=auth_cookie_headers(user.id),
    )
    names = [item["file_name"] for item in response.json()["items"]]
    assert names == ["aaa.pdf", "zzz.pdf"]


async def test_list_documents_pagination(client, db_session):
    user = await make_user(db_session)
    for i in range(3):
        await _upload_document(client, user.id, file_name=f"doc{i}.pdf")

    response = await client.get(
        "/api/v1/documents",
        params={"limit": 2, "offset": 0},
        headers=auth_cookie_headers(user.id),
    )
    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3


# --- FR-DOC-003 detail/download/content ---


async def test_get_document_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _upload_document(client, owner.id)

    response = await client.get(
        f"/api/v1/documents/{document['id']}", headers=auth_cookie_headers(attacker.id)
    )
    assert response.status_code == 404


async def test_get_document_unknown_id_returns_404(client, db_session):
    user = await make_user(db_session)
    response = await client.get(
        f"/api/v1/documents/{uuid.uuid4()}", headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 404


async def test_download_returns_presigned_url(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)

    response = await client.get(
        f"/api/v1/documents/{document['id']}/download",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"download_url", "expires_in"}


async def test_content_not_ready_returns_409(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)  # still status=queued

    response = await client.get(
        f"/api/v1/documents/{document['id']}/content",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_ready"


async def test_content_ready_txt_returns_text(client, db_session):
    """Simulates what R3's worker will eventually do (set status=ready +
    populate document_chunks) — R3 doesn't exist yet, so the test drives
    the repository directly, exactly as tasks/remediation-plan.md R2 §5.2
    anticipated for the SSE endpoint and equally applicable here."""
    from app.repositories.document_repository import (
        DocumentChunkRepository,
        DocumentRepository,
    )

    user = await make_user(db_session)
    document = await _upload_document(
        client, user.id, file_name="a.txt", mime_type="text/plain", data=TXT_BYTES
    )
    doc_repo = DocumentRepository(db_session)
    await doc_repo.set_status(user.id, uuid.UUID(document["id"]), status="ready")
    await DocumentChunkRepository(db_session).bulk_create(
        user.id,
        uuid.UUID(document["id"]),
        [{"chunk_index": 0, "content": "hello world", "token_count": 2}],
    )

    response = await client.get(
        f"/api/v1/documents/{document['id']}/content",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200
    assert response.json() == {"text": "hello world"}


async def test_content_ready_pdf_groups_chunks_by_page(client, db_session):
    from app.repositories.document_repository import (
        DocumentChunkRepository,
        DocumentRepository,
    )

    user = await make_user(db_session)
    document = await _upload_document(client, user.id)
    doc_repo = DocumentRepository(db_session)
    await doc_repo.set_status(user.id, uuid.UUID(document["id"]), status="ready")
    await DocumentChunkRepository(db_session).bulk_create(
        user.id,
        uuid.UUID(document["id"]),
        [
            {
                "chunk_index": 0,
                "content": "page one part a",
                "page_number": 1,
                "token_count": 4,
            },
            {
                "chunk_index": 1,
                "content": "page one part b",
                "page_number": 1,
                "token_count": 4,
            },
            {
                "chunk_index": 2,
                "content": "page two",
                "page_number": 2,
                "token_count": 2,
            },
        ],
    )

    response = await client.get(
        f"/api/v1/documents/{document['id']}/content",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["pages"] == [
        {"page_number": 1, "text": "page one part a\npage one part b"},
        {"page_number": 2, "text": "page two"},
    ]


async def test_content_pdf_page_query_param_filters_to_one_page(client, db_session):
    from app.repositories.document_repository import (
        DocumentChunkRepository,
        DocumentRepository,
    )

    user = await make_user(db_session)
    document = await _upload_document(client, user.id)
    doc_repo = DocumentRepository(db_session)
    await doc_repo.set_status(user.id, uuid.UUID(document["id"]), status="ready")
    await DocumentChunkRepository(db_session).bulk_create(
        user.id,
        uuid.UUID(document["id"]),
        [
            {
                "chunk_index": 0,
                "content": "page one",
                "page_number": 1,
                "token_count": 2,
            },
            {
                "chunk_index": 1,
                "content": "page two",
                "page_number": 2,
                "token_count": 2,
            },
        ],
    )

    response = await client.get(
        f"/api/v1/documents/{document['id']}/content",
        params={"page": 2},
        headers=auth_cookie_headers(user.id),
    )
    assert response.json()["pages"] == [{"page_number": 2, "text": "page two"}]


async def test_content_ready_csv_returns_rows_and_columns(client, db_session):
    from app.repositories.document_repository import (
        DocumentChunkRepository,
        DocumentRepository,
    )

    user = await make_user(db_session)
    csv_bytes = b"name,age\nAlice,30\nBob,25\n"
    document = await _upload_document(
        client, user.id, file_name="a.csv", mime_type="text/csv", data=csv_bytes
    )
    doc_repo = DocumentRepository(db_session)
    await doc_repo.set_status(user.id, uuid.UUID(document["id"]), status="ready")
    await DocumentChunkRepository(db_session).bulk_create(
        user.id,
        uuid.UUID(document["id"]),
        [
            {
                "chunk_index": 0,
                "content": "name,age\nAlice,30\nBob,25",
                "token_count": 8,
            }
        ],
    )

    response = await client.get(
        f"/api/v1/documents/{document['id']}/content",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["name", "age"]
    assert body["rows"] == [
        {"name": "Alice", "age": "30"},
        {"name": "Bob", "age": "25"},
    ]


async def test_content_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _upload_document(client, owner.id)

    response = await client.get(
        f"/api/v1/documents/{document['id']}/content",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


# --- FR-DOC-004 rename / FR-DOC-006 tags ---


async def test_update_document_renames(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)

    response = await client.patch(
        f"/api/v1/documents/{document['id']}",
        json={"file_name": "renamed.pdf"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200
    assert response.json()["file_name"] == "renamed.pdf"


async def test_update_document_empty_name_rejected(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)

    response = await client.patch(
        f"/api/v1/documents/{document['id']}",
        json={"file_name": ""},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_update_document_assigns_tags(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)
    tag = await client.post(
        "/api/v1/tags", json={"name": "Important"}, headers=auth_cookie_headers(user.id)
    )
    tag_id = tag.json()["id"]

    response = await client.patch(
        f"/api/v1/documents/{document['id']}",
        json={"tag_ids": [tag_id]},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200
    assert len(response.json()["tags"]) == 1
    assert response.json()["tags"][0]["name"] == "Important"


async def test_update_document_rejects_another_users_tag(client, db_session):
    user = await make_user(db_session)
    other = await make_user(db_session)
    document = await _upload_document(client, user.id)
    other_tag = await client.post(
        "/api/v1/tags", json={"name": "NotYours"}, headers=auth_cookie_headers(other.id)
    )

    response = await client.patch(
        f"/api/v1/documents/{document['id']}",
        json={"tag_ids": [other_tag.json()["id"]]},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404


async def test_update_document_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _upload_document(client, owner.id)

    response = await client.patch(
        f"/api/v1/documents/{document['id']}",
        json={"file_name": "hijacked.pdf"},
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


# --- FR-DOC-005 delete ---


async def test_delete_document_removes_from_list(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)

    response = await client.delete(
        f"/api/v1/documents/{document['id']}", headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 204

    listing = await client.get(
        "/api/v1/documents", headers=auth_cookie_headers(user.id)
    )
    assert listing.json()["total"] == 0

    detail = await client.get(
        f"/api/v1/documents/{document['id']}", headers=auth_cookie_headers(user.id)
    )
    assert detail.status_code == 404


async def test_delete_document_releases_storage_quota(client, db_session):
    from app.repositories.user_repository import UserRepository

    user = await make_user(db_session)
    document = await _upload_document(client, user.id)
    await client.delete(
        f"/api/v1/documents/{document['id']}", headers=auth_cookie_headers(user.id)
    )

    refreshed = await UserRepository(db_session).get_by_id(user.id)
    assert refreshed.storage_used_bytes == 0


async def test_delete_document_cross_tenant_returns_404(client, db_session):
    """testing.md §3.5 — 404, not 403 (FR-DOC-005's own acceptance criterion)."""
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _upload_document(client, owner.id)

    response = await client.delete(
        f"/api/v1/documents/{document['id']}", headers=auth_cookie_headers(attacker.id)
    )
    assert response.status_code == 404

    # The owner's document is untouched.
    still_there = await client.get(
        f"/api/v1/documents/{document['id']}", headers=auth_cookie_headers(owner.id)
    )
    assert still_there.status_code == 200


async def test_delete_unknown_document_returns_404(client, db_session):
    user = await make_user(db_session)
    response = await client.delete(
        f"/api/v1/documents/{uuid.uuid4()}", headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 404


# --- FR-PROC-005 reprocess ---


async def test_reprocess_requires_failed_status(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)  # status=queued, not failed

    response = await client.post(
        f"/api/v1/documents/{document['id']}/reprocess",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status"


async def test_reprocess_failed_document_resets_to_queued(client, db_session):
    from app.repositories.document_repository import DocumentRepository

    user = await make_user(db_session)
    document = await _upload_document(client, user.id)
    doc_repo = DocumentRepository(db_session)
    await doc_repo.set_status(
        user.id,
        uuid.UUID(document["id"]),
        status="failed",
        processing_error="parse error",
    )

    response = await client.post(
        f"/api/v1/documents/{document['id']}/reprocess",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"

    detail = await client.get(
        f"/api/v1/documents/{document['id']}", headers=auth_cookie_headers(user.id)
    )
    assert detail.json()["processing_error"] is None


# --- FR-DOC-008 status ---


async def test_get_status_polling(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)

    response = await client.get(
        f"/api/v1/documents/{document['id']}/status",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "processing_error": None}


async def test_get_status_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _upload_document(client, owner.id)

    response = await client.get(
        f"/api/v1/documents/{document['id']}/status",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


# --- FR-DOC-007 bulk (P2) ---


async def test_bulk_delete_skips_unowned_documents_silently(client, db_session):
    """api.md — unowned IDs are silently counted in `skipped`, never a
    partial error (avoids existence leakage across a batch)."""
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    own_doc = await _upload_document(client, owner.id)
    other_doc = await _upload_document(client, attacker.id)

    response = await client.post(
        "/api/v1/documents/bulk",
        json={"document_ids": [own_doc["id"], other_doc["id"]], "action": "delete"},
        headers=auth_cookie_headers(owner.id),
    )
    assert response.status_code == 200
    assert response.json() == {"affected": 1, "skipped": 1}


async def test_bulk_tag_requires_tag_ids(client, db_session):
    user = await make_user(db_session)
    document = await _upload_document(client, user.id)

    response = await client.post(
        "/api/v1/documents/bulk",
        json={"document_ids": [document["id"]], "action": "tag"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422


async def test_bulk_tag_applies_to_all_owned_documents(client, db_session):
    user = await make_user(db_session)
    doc_a = await _upload_document(client, user.id, file_name="a.pdf")
    doc_b = await _upload_document(client, user.id, file_name="b.pdf")
    tag = await client.post(
        "/api/v1/tags", json={"name": "Batch"}, headers=auth_cookie_headers(user.id)
    )
    tag_id = tag.json()["id"]

    response = await client.post(
        "/api/v1/documents/bulk",
        json={
            "document_ids": [doc_a["id"], doc_b["id"]],
            "action": "tag",
            "tag_ids": [tag_id],
        },
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 200
    assert response.json() == {"affected": 2, "skipped": 0}


# --- unauthorized access ---


async def test_list_documents_without_cookie_returns_401(client):
    response = await client.get("/api/v1/documents")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_presign_without_cookie_returns_401(client):
    response = await client.post(
        "/api/v1/documents/presign",
        json={"file_name": "a.pdf", "mime_type": "application/pdf", "size_bytes": 10},
    )
    assert response.status_code == 401

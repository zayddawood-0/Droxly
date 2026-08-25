"""
tasks/remediation-plan.md R3 — end-to-end document-processing integration
tests: real Postgres (via the shared `client`/`db_session` fixtures, per
this suite's existing convention), the real local StorageProvider, real
Redis (for the enqueue assertion), and FakeEmbeddingProvider. Exercises the
DocumentProcessingService directly against the same session the API used
to create the row — the worker's own sync-entrypoint/retry mechanics are
covered separately in test_document_processing_worker.py; this file's
concern is the pipeline's actual behavior per MIME type plus R2<->R3's
confirm/reprocess integration contract.
"""

import io
import uuid
from urllib.parse import urlparse

import pytest

from app.ai.embeddings import FakeEmbeddingProvider
from app.core.queue import get_document_processing_queue
from app.core.storage import get_storage_provider
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.services.document_processing_service import DocumentProcessingService
from tests._pdf_fixtures import build_text_pdf
from tests.conftest import auth_cookie_headers, make_user

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _build_docx_bytes(text: str) -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def _path_of(url: str) -> str:
    return urlparse(url).path


async def _upload_document(client, user_id, *, file_name, mime_type, data) -> uuid.UUID:
    presign = await client.post(
        "/api/v1/documents/presign",
        json={"file_name": file_name, "mime_type": mime_type, "size_bytes": len(data)},
        headers=auth_cookie_headers(user_id),
    )
    assert presign.status_code == 201, presign.text
    body = presign.json()
    document_id = uuid.UUID(body["document_id"])

    put_response = await client.put(_path_of(body["upload_url"]), content=data)
    assert put_response.status_code == 200

    confirm = await client.post(
        f"/api/v1/documents/{document_id}/confirm", headers=auth_cookie_headers(user_id)
    )
    assert confirm.status_code == 202, confirm.text
    return document_id


async def test_confirm_upload_enqueues_a_real_processing_job(client, db_session):
    """R2<->R3 integration contract — confirm_upload no longer leaves the
    document queued with nothing consuming it (the documented R2 gap this
    task closes)."""
    user = await make_user(db_session)
    queue = get_document_processing_queue()
    before = queue.count

    await _upload_document(
        client,
        user.id,
        file_name="a.txt",
        mime_type="text/plain",
        data=b"hello world",
    )

    assert queue.count == before + 1


@pytest.mark.parametrize(
    ("mime_type", "file_name", "build_data"),
    [
        (
            "application/pdf",
            "a.pdf",
            lambda: build_text_pdf(["Real page one text content."]),
        ),
        (DOCX_MIME, "a.docx", lambda: _build_docx_bytes("Real paragraph content.")),
        ("text/plain", "a.txt", lambda: b"Real plain text content for processing."),
        ("text/csv", "a.csv", lambda: b"name,score\nAlice,95\nBob,88\n"),
    ],
)
async def test_full_pipeline_reaches_ready_for_every_supported_mime_type(
    client, db_session, mime_type, file_name, build_data
):
    """FR-PROC-001..003 — extract -> chunk -> embed -> ready, for every
    format document-processing.md defines, driven through the real API
    upload flow and then the real processing service (no worker/queue
    indirection needed to assert the pipeline's own correctness)."""
    user = await make_user(db_session)
    data = build_data()
    document_id = await _upload_document(
        client, user.id, file_name=file_name, mime_type=mime_type, data=data
    )

    service = DocumentProcessingService(
        DocumentRepository(db_session),
        DocumentChunkRepository(db_session),
        get_storage_provider(),
        FakeEmbeddingProvider(),
    )
    await service.process_document(user.id, document_id)

    document = await DocumentRepository(db_session).get(user.id, document_id)
    assert document.status == "ready"
    assert document.extracted_text_available is True

    chunks = await DocumentChunkRepository(db_session).list_for_document(
        user.id, document_id
    )
    assert len(chunks) > 0
    assert all(chunk.embedding is not None for chunk in chunks)

    if mime_type == "application/pdf":
        assert document.page_count == 1
        assert chunks[0].page_number == 1
    if mime_type == "text/csv":
        assert chunks[0].content.splitlines()[0] == "name,score"


async def test_reprocess_clears_prior_chunks_and_enqueues_a_new_job(client, db_session):
    user = await make_user(db_session)
    document_id = await _upload_document(
        client,
        user.id,
        file_name="a.txt",
        mime_type="text/plain",
        data=b"original content before reprocessing",
    )

    service = DocumentProcessingService(
        DocumentRepository(db_session),
        DocumentChunkRepository(db_session),
        get_storage_provider(),
        FakeEmbeddingProvider(),
    )
    await service.process_document(user.id, document_id)
    original_chunks = await DocumentChunkRepository(db_session).list_for_document(
        user.id, document_id
    )
    assert len(original_chunks) > 0

    # Simulate a document that later needs reprocessing (api.md: only a
    # `failed` document may be reprocessed via this route).
    await DocumentRepository(db_session).set_status(
        user.id, document_id, status="failed", processing_error="simulated"
    )

    queue = get_document_processing_queue()
    before = queue.count

    response = await client.post(
        f"/api/v1/documents/{document_id}/reprocess",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 202, response.text

    remaining_chunks = await DocumentChunkRepository(db_session).list_for_document(
        user.id, document_id
    )
    assert remaining_chunks == []  # "discarded and replaced, not appended" (api.md)
    assert queue.count == before + 1

    document = await DocumentRepository(db_session).get(user.id, document_id)
    assert document.status == "queued"
    assert document.processing_error is None


async def test_process_document_never_touches_another_users_document(
    client, db_session
):
    """Mandatory cross-tenant category (testing.md §3.5) applied to the
    processing pipeline itself, not just the HTTP layer."""
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document_id = await _upload_document(
        client,
        owner.id,
        file_name="a.txt",
        mime_type="text/plain",
        data=b"owner's private document content",
    )

    service = DocumentProcessingService(
        DocumentRepository(db_session),
        DocumentChunkRepository(db_session),
        get_storage_provider(),
        FakeEmbeddingProvider(),
    )
    await service.process_document(attacker.id, document_id)  # wrong user_id

    document = await DocumentRepository(db_session).get(owner.id, document_id)
    assert document.status == "queued"  # untouched — the attacker's call was a no-op
    chunks = await DocumentChunkRepository(db_session).list_for_document(
        owner.id, document_id
    )
    assert chunks == []

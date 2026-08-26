"""
api.md §6 (/extractions) — tasks/remediation-plan.md R5. Full HTTP-layer
contract tests: exact request/response shapes and error envelopes, auth,
tenant isolation, and document-state preconditions. The extraction *run*
itself (the background worker/graph) is covered by
test_extraction_processing_service.py and test_extraction_worker.py — these
tests only ever exercise the trigger/CRUD half (`ExtractionService`), so
every extraction here is created and then directly persisted to its
terminal state via the repository, exactly as a real worker eventually
would, rather than re-driving the whole graph.
"""

import uuid

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.graphs.extraction import PRESET_TEMPLATES
from app.core.queue import get_extraction_queue
from app.models import Document, DocumentChunk
from app.repositories.extraction_repository import ExtractionRepository
from tests.conftest import auth_cookie_headers, make_user

INVOICE_SCHEMA = PRESET_TEMPLATES["invoice"]["fields"]


async def _make_ready_document(db_session, user_id, *, content: str = "content"):
    document = Document(
        user_id=user_id,
        file_name="invoice.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="ready",
    )
    db_session.add(document)
    await db_session.flush()
    provider = FakeEmbeddingProvider()
    [vector] = await provider.embed_batch([content])
    db_session.add(
        DocumentChunk(
            user_id=user_id,
            document_id=document.id,
            chunk_index=0,
            content=content,
            page_number=1,
            char_start=0,
            char_end=len(content),
            token_count=len(content.split()),
            embedding=vector,
            embedding_model=provider.model_name,
        )
    )
    await db_session.flush()
    return document


async def _make_completed_extraction(
    db_session, user_id, document_id, *, template_key="invoice", schema=None
):
    return await ExtractionRepository(db_session).create(
        user_id,
        document_id=document_id,
        template_key=template_key,
        schema_json=schema if schema is not None else INVOICE_SCHEMA,
        result_json=[
            {
                "field": "invoice_number",
                "value": "123",
                "original_value": "123",
                "confidence": 0.9,
                "not_found_reason": None,
                "citation": {"page_number": 1, "snippet": "Invoice #123"},
                "corrected": False,
            },
            {
                "field": "due_date",
                "value": None,
                "original_value": None,
                "confidence": None,
                "not_found_reason": "not mentioned in the document",
                "citation": None,
                "corrected": False,
            },
        ],
        status="completed",
    )


# --- GET /extractions/templates ---


async def test_list_templates_returns_the_four_named_presets_with_full_metadata(
    client, db_session
):
    user = await make_user(db_session)
    response = await client.get(
        "/api/v1/extractions/templates", headers=auth_cookie_headers(user.id)
    )
    assert response.status_code == 200
    body = response.json()
    keys = {item["key"] for item in body["items"]}
    assert keys == {"invoice", "contract", "resume", "research_paper"}
    invoice = next(item for item in body["items"] if item["key"] == "invoice")
    assert invoice["name"] == "Invoice"
    assert isinstance(invoice["description"], str) and invoice["description"]
    field_names = {f["name"] for f in invoice["fields"]}
    assert "invoice_number" in field_names
    invoice_number_field = next(
        f for f in invoice["fields"] if f["name"] == "invoice_number"
    )
    assert invoice_number_field["type"] == "string"
    assert invoice_number_field["required"] is True


async def test_list_templates_requires_auth(client):
    response = await client.get("/api/v1/extractions/templates")
    assert response.status_code == 401


# --- POST /extractions ---


async def test_create_extraction_with_template_key_returns_202_processing(
    client, db_session
):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    response = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(document.id), "template_key": "invoice"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "processing"
    assert uuid.UUID(body["id"])


async def test_create_extraction_with_custom_schema_returns_202_processing(
    client, db_session
):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    response = await client.post(
        "/api/v1/extractions",
        json={
            "document_id": str(document.id),
            "schema": [
                {"name": "custom_field", "type": "string", "required": True},
            ],
        },
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "processing"


async def test_create_extraction_requires_exactly_one_of_template_key_or_schema(
    client, db_session
):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    neither = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(document.id)},
        headers=auth_cookie_headers(user.id),
    )
    assert neither.status_code == 422
    assert neither.json()["error"]["code"] == "validation_error"

    both = await client.post(
        "/api/v1/extractions",
        json={
            "document_id": str(document.id),
            "template_key": "invoice",
            "schema": [{"name": "x", "type": "string", "required": False}],
        },
        headers=auth_cookie_headers(user.id),
    )
    assert both.status_code == 422
    assert both.json()["error"]["code"] == "validation_error"


async def test_create_extraction_rejects_unknown_template_key(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    response = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(document.id), "template_key": "not_a_real_template"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_create_extraction_rejects_generic_as_a_template_key(client, db_session):
    """`generic` is the graph's own internal last-resort fallback (langgraph.md
    §4), never a user-selectable preset (api.md §6 lists only the four named
    templates) — must 422 exactly like any other unknown key."""
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)

    response = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(document.id), "template_key": "generic"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422


async def test_create_extraction_404s_for_a_document_that_does_not_exist(
    client, db_session
):
    user = await make_user(db_session)
    response = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(uuid.uuid4()), "template_key": "invoice"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_create_extraction_404s_for_another_users_document(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _make_ready_document(db_session, owner.id)

    response = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(document.id), "template_key": "invoice"},
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


async def test_create_extraction_409s_when_document_is_not_ready(client, db_session):
    user = await make_user(db_session)
    document = Document(
        user_id=user.id,
        file_name="still-processing.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="queued",
    )
    db_session.add(document)
    await db_session.flush()

    response = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(document.id), "template_key": "invoice"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_create_extraction_enqueues_exactly_one_job(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    queue = get_extraction_queue()
    before = queue.count

    response = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(document.id), "template_key": "invoice"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 202
    assert queue.count == before + 1


async def test_create_extraction_requires_auth(client, db_session):
    response = await client.post(
        "/api/v1/extractions",
        json={"document_id": str(uuid.uuid4()), "template_key": "invoice"},
    )
    assert response.status_code == 401


# --- GET /extractions/{id} ---


async def test_get_extraction_returns_the_exact_documented_shape(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    extraction = await _make_completed_extraction(db_session, user.id, document.id)

    response = await client.get(
        f"/api/v1/extractions/{extraction.id}", headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(extraction.id)
    assert body["document_id"] == str(document.id)
    assert body["template_key"] == "invoice"
    assert body["status"] == "completed"
    assert "created_at" in body
    assert {f["name"] for f in body["schema"]} == {f["name"] for f in INVOICE_SCHEMA}
    result_by_field = {r["field"]: r for r in body["result"]}
    assert result_by_field["invoice_number"]["value"] == "123"
    assert result_by_field["invoice_number"]["citation"] == {
        "page_number": 1,
        "snippet": "Invoice #123",
    }
    assert result_by_field["invoice_number"]["corrected"] is False
    assert result_by_field["due_date"]["value"] is None
    assert result_by_field["due_date"]["not_found_reason"] == (
        "not mentioned in the document"
    )
    # api.md PATCH: the model's original value is retained internally but
    # never surfaced in the response.
    assert "original_value" not in result_by_field["invoice_number"]


async def test_get_extraction_404s_for_missing_or_other_users_extraction(
    client, db_session
):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _make_ready_document(db_session, owner.id)
    extraction = await _make_completed_extraction(db_session, owner.id, document.id)

    missing = await client.get(
        f"/api/v1/extractions/{uuid.uuid4()}", headers=auth_cookie_headers(owner.id)
    )
    assert missing.status_code == 404

    cross_tenant = await client.get(
        f"/api/v1/extractions/{extraction.id}", headers=auth_cookie_headers(attacker.id)
    )
    assert cross_tenant.status_code == 404


# --- GET /documents/{document_id}/extractions ---


async def test_list_document_extractions_returns_paginated_summaries(
    client, db_session
):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    first = await _make_completed_extraction(db_session, user.id, document.id)
    second = await _make_completed_extraction(db_session, user.id, document.id)

    response = await client.get(
        f"/api/v1/documents/{document.id}/extractions",
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
        assert set(item.keys()) == {"id", "template_key", "status", "created_at"}


async def test_list_document_extractions_404s_for_another_users_document(
    client, db_session
):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _make_ready_document(db_session, owner.id)
    await _make_completed_extraction(db_session, owner.id, document.id)

    response = await client.get(
        f"/api/v1/documents/{document.id}/extractions",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


# --- PATCH /extractions/{id} ---


async def test_patch_extraction_corrects_a_field_and_marks_it_corrected(
    client, db_session
):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    extraction = await _make_completed_extraction(db_session, user.id, document.id)

    response = await client.patch(
        f"/api/v1/extractions/{extraction.id}",
        json={"corrections": [{"field": "invoice_number", "value": "999"}]},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    result_by_field = {r["field"]: r for r in body["result"]}
    assert result_by_field["invoice_number"]["value"] == "999"
    assert result_by_field["invoice_number"]["corrected"] is True
    # Untouched fields keep their original value/corrected=False.
    assert result_by_field["due_date"]["corrected"] is False

    persisted = await ExtractionRepository(db_session).get(user.id, extraction.id)
    persisted_by_field = {item["field"]: item for item in persisted.result_json}
    assert persisted_by_field["invoice_number"]["value"] == "999"
    assert persisted_by_field["invoice_number"]["original_value"] == "123"


async def test_patch_extraction_422s_for_a_field_not_in_the_schema(client, db_session):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    extraction = await _make_completed_extraction(db_session, user.id, document.id)

    response = await client.patch(
        f"/api/v1/extractions/{extraction.id}",
        json={"corrections": [{"field": "not_a_real_field", "value": "x"}]},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_field"


async def test_patch_extraction_404s_for_another_users_extraction(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    document = await _make_ready_document(db_session, owner.id)
    extraction = await _make_completed_extraction(db_session, owner.id, document.id)

    response = await client.patch(
        f"/api/v1/extractions/{extraction.id}",
        json={"corrections": [{"field": "invoice_number", "value": "999"}]},
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404

    unchanged = await ExtractionRepository(db_session).get(owner.id, extraction.id)
    by_field = {item["field"]: item for item in unchanged.result_json}
    assert by_field["invoice_number"]["value"] == "123"  # untouched

"""
api.md §8 (/search) — tasks/remediation-plan.md R8. Full HTTP-layer contract
tests: exact response shape, query validation, cross-tenant isolation,
pagination envelope, filters, and the `ai_requests` observability row every
embedding-provider call must produce (`NFR-OBS-001`).
"""

import uuid

from app.ai.embeddings import FakeEmbeddingProvider
from app.models import Document
from app.repositories.document_repository import DocumentChunkRepository
from app.repositories.observability_repository import AiRequestRepository
from tests.conftest import auth_cookie_headers, make_user

_provider = FakeEmbeddingProvider()


async def _make_document(
    db_session,
    user_id: uuid.UUID,
    *,
    file_name: str = "report.pdf",
    mime_type: str = "application/pdf",
    status: str = "ready",
) -> Document:
    document = Document(
        user_id=user_id,
        file_name=file_name,
        storage_key=str(uuid.uuid4()),
        mime_type=mime_type,
        size_bytes=1024,
        checksum_sha256="a" * 64,
        status=status,
    )
    db_session.add(document)
    await db_session.flush()
    return document


async def _add_chunk(
    db_session, user_id, document_id, content: str, *, page_number: int = 1
) -> None:
    [vector] = await _provider.embed_batch([content])
    await DocumentChunkRepository(db_session).bulk_create(
        user_id,
        document_id,
        [
            {
                "chunk_index": 0,
                "content": content,
                "page_number": page_number,
                "char_start": 0,
                "char_end": len(content),
                "token_count": len(content.split()),
                "embedding": vector,
                "embedding_model": _provider.model_name,
            }
        ],
    )


async def test_search_returns_the_exact_documented_shape(client, db_session):
    user = await make_user(db_session)
    doc = await _make_document(db_session, user.id, file_name="quarterly.pdf")
    await _add_chunk(
        db_session, user.id, doc.id, "quarterly revenue increased significantly"
    )

    response = await client.get(
        "/api/v1/search",
        params={"q": "quarterly revenue"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    item = body["items"][0]
    assert set(item.keys()) == {
        "document_id",
        "file_name",
        "snippet",
        "relevance_score",
        "matched_page",
    }
    assert item["document_id"] == str(doc.id)
    assert item["file_name"] == "quarterly.pdf"
    assert item["matched_page"] == 1
    assert isinstance(item["relevance_score"], float)
    snippet = item["snippet"]
    assert set(snippet.keys()) == {"text", "highlights"}
    assert isinstance(snippet["text"], str)
    for h in snippet["highlights"]:
        assert set(h.keys()) == {"start", "end"}
        assert h["start"] < h["end"]
        matched = snippet["text"][h["start"] : h["end"]]
        assert matched.lower() in {"quarterly", "revenue"}


async def test_search_requires_auth(client, db_session):
    response = await client.get("/api/v1/search", params={"q": "anything"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_search_422s_for_empty_query(client, db_session):
    user = await make_user(db_session)

    response = await client.get(
        "/api/v1/search", params={"q": ""}, headers=auth_cookie_headers(user.id)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_search_422s_when_date_from_is_after_date_to(client, db_session):
    user = await make_user(db_session)

    response = await client.get(
        "/api/v1/search",
        params={"q": "anything", "date_from": "2026-06-01", "date_to": "2026-01-01"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"


async def test_search_returns_empty_results_for_no_match(client, db_session):
    user = await make_user(db_session)
    doc = await _make_document(db_session, user.id)
    await _add_chunk(db_session, user.id, doc.id, "something entirely different")

    response = await client.get(
        "/api/v1/search",
        params={"q": "nonexistent gibberish zzqx"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_search_never_returns_another_users_documents(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    doc = await _make_document(db_session, owner.id, file_name="private-plan.pdf")
    await _add_chunk(db_session, owner.id, doc.id, "confidential acquisition terms")

    response = await client.get(
        "/api/v1/search",
        params={"q": "confidential acquisition"},
        headers=auth_cookie_headers(attacker.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_search_filters_narrow_results(client, db_session):
    user = await make_user(db_session)
    pdf_doc = await _make_document(
        db_session, user.id, file_name="a.pdf", mime_type="application/pdf"
    )
    txt_doc = await _make_document(
        db_session, user.id, file_name="b.txt", mime_type="text/plain"
    )
    await _add_chunk(db_session, user.id, pdf_doc.id, "shared keyword payload")
    await _add_chunk(db_session, user.id, txt_doc.id, "shared keyword payload")

    response = await client.get(
        "/api/v1/search",
        params={"q": "shared keyword", "mime_type": "text/plain"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["document_id"] == str(txt_doc.id)


async def test_search_pagination_envelope(client, db_session):
    user = await make_user(db_session)
    doc = await _make_document(db_session, user.id)
    for i in range(3):
        await DocumentChunkRepository(db_session).bulk_create(
            user.id,
            doc.id,
            [
                {
                    "chunk_index": i + 1,
                    "content": f"pagination probe term section {i}",
                    "page_number": i + 1,
                    "char_start": 0,
                    "char_end": 10,
                    "token_count": 5,
                    "embedding": (await _provider.embed_batch(["x"]))[0],
                    "embedding_model": _provider.model_name,
                }
            ],
        )

    response = await client.get(
        "/api/v1/search",
        params={"q": "pagination probe", "limit": 2, "offset": 0},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) == 2


async def test_search_logs_one_ai_requests_row_for_the_embedding_call(
    client, db_session
):
    user = await make_user(db_session)
    doc = await _make_document(db_session, user.id)
    await _add_chunk(db_session, user.id, doc.id, "observability probe content")

    response = await client.get(
        "/api/v1/search",
        params={"q": "observability probe"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 200
    rows = await AiRequestRepository(db_session).list(user.id, limit=10)
    embedding_rows = [r for r in rows if r.operation == "embedding"]
    assert len(embedding_rows) == 1
    assert embedding_rows[0].status == "success"
    assert embedding_rows[0].provider == _provider.provider_name
    assert (
        embedding_rows[0].input_tokens is not None
        and embedding_rows[0].input_tokens > 0
    )


async def test_search_snippet_text_is_never_html_escaped_or_transformed(
    client, db_session
):
    """
    security.md §6.2 — the backend returns the raw excerpt verbatim (no
    HTML/markup construction server-side); the already-built frontend is
    responsible for safe rendering via offsets, not string content.
    """
    user = await make_user(db_session)
    doc = await _make_document(db_session, user.id)
    await _add_chunk(
        db_session, user.id, doc.id, "a <script>alert(1)</script> probe payload"
    )

    response = await client.get(
        "/api/v1/search",
        params={"q": "probe payload"},
        headers=auth_cookie_headers(user.id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    snippet_text = body["items"][0]["snippet"]["text"]
    assert "<script>" in snippet_text
    assert "&lt;" not in snippet_text

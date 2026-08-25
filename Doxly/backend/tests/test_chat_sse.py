"""
tasks/remediation-plan.md R4 §7.1 — the exact Chat SSE contract (api.md §4),
asserted event-by-event, not merely "a stream occurred". Full HTTP-layer
tests (real transport, real CSRF/rate-limit dependency chain, only
overriding the LLM/embedding providers for determinism) rather than
skipping straight to unit-level calls, so the actual wiring is exercised.
"""

import json
import uuid

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.llm import FakeLLMProvider, get_llm_provider
from app.main import app
from app.models import Document, DocumentChunk
from tests.conftest import auth_cookie_headers, make_user

CHUNK_CONTENT = (
    "Quarterly revenue grew twelve percent year over year according to the report."
)
MATCHING_QUERY = "revenue grew twelve percent year over year"
GROUNDED_ANSWER = "Revenue grew twelve percent year over year."


async def _make_ready_document(db_session, user_id, *, file_name="report.pdf"):
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


async def _seed_chunk(db_session, user_id, document_id, content: str) -> None:
    provider = FakeEmbeddingProvider()
    [vector] = await provider.embed_batch([content])
    chunk = DocumentChunk(
        user_id=user_id,
        document_id=document_id,
        chunk_index=0,
        content=content,
        page_number=1,
        char_start=0,
        char_end=len(content),
        token_count=len(content.split()),
        embedding=vector,
        embedding_model=provider.model_name,
    )
    db_session.add(chunk)
    await db_session.flush()


def _override_llm(responses: list[str]) -> FakeLLMProvider:
    provider = FakeLLMProvider(responses=responses)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return provider


def _clear_llm_override() -> None:
    app.dependency_overrides.pop(get_llm_provider, None)


async def _parse_sse(response) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            raw_event, buffer = buffer.split("\n\n", 1)
            event_name = None
            data = None
            for line in raw_event.splitlines():
                if line.startswith("event: "):
                    event_name = line[len("event: ") :]
                elif line.startswith("data: "):
                    data = json.loads(line[len("data: ") :])
            if event_name is not None:
                events.append((event_name, data))
    return events


async def test_full_event_sequence_for_a_grounded_answer(client, db_session):
    """factual_qa -> retrieval finds a chunk -> generation -> grounded ->
    message_id, token(s), citations, done, in that exact order."""
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    await _seed_chunk(db_session, user.id, document.id, CHUNK_CONTENT)

    create = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(document.id)]},
        headers=auth_cookie_headers(user.id),
    )
    conversation_id = create.json()["id"]

    _override_llm(responses=["factual_qa", GROUNDED_ANSWER])
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": MATCHING_QUERY},
            headers=auth_cookie_headers(user.id),
        ) as response:
            assert response.status_code == 200
            events = await _parse_sse(response)
    finally:
        _clear_llm_override()

    names = [name for name, _ in events]
    assert names[0] == "message_id"
    assert names[-2:] == ["citations", "done"]
    assert names.count("token") >= 1
    assert set(names) == {"message_id", "token", "citations", "done"}

    full_text = "".join(
        data["text"] for name, data in events if name == "token"
    ).strip()
    assert full_text == GROUNDED_ANSWER

    citations_event = next(data for name, data in events if name == "citations")
    assert len(citations_event["citations"]) == 1
    assert citations_event["citations"][0]["document_id"] == str(document.id)
    assert citations_event["citations"][0]["page_number"] == 1

    # Persistence: user + assistant messages, citation row, conversation touched.
    detail = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(user.id),
    )
    messages = detail.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == MATCHING_QUERY
    assert messages[1]["content"] == GROUNDED_ANSWER
    assert len(messages[1]["citations"]) == 1


async def test_out_of_scope_query_skips_retrieval_and_generation(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]

    provider = _override_llm(responses=["out_of_scope"])
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "hi there, how are you?"},
            headers=auth_cookie_headers(user.id),
        ) as response:
            events = await _parse_sse(response)
    finally:
        _clear_llm_override()

    assert len(provider.calls) == 1  # classifier only
    names = [name for name, _ in events]
    assert names[0] == "message_id"
    assert names[-2:] == ["citations", "done"]
    assert set(names) == {"message_id", "token", "citations", "done"}
    citations_event = next(data for name, data in events if name == "citations")
    assert citations_event["citations"] == []
    full_text = "".join(
        data["text"] for name, data in events if name == "token"
    ).strip()
    assert full_text == "I can only answer questions about your documents."


async def test_no_relevant_context_yields_graceful_decline(client, db_session):
    """FR-AI-004/FR-RAG-003 — a query with nothing relevant retrieved (no
    chunks exist at all) declines rather than fabricating."""
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    create = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(document.id)]},
        headers=auth_cookie_headers(user.id),
    )
    conversation_id = create.json()["id"]

    _override_llm(responses=["factual_qa"])
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "what does the document say?"},
            headers=auth_cookie_headers(user.id),
        ) as response:
            events = await _parse_sse(response)
    finally:
        _clear_llm_override()

    full_text = "".join(
        data["text"] for name, data in events if name == "token"
    ).strip()
    assert "don't contain information relevant" in full_text
    citations_event = next(data for name, data in events if name == "citations")
    assert citations_event["citations"] == []


async def test_ungrounded_generation_falls_back_to_no_answer(client, db_session):
    """FR-AI-004 — even with retrieved context, an answer that doesn't
    actually draw on it is replaced with the safe decline, never shown."""
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    await _seed_chunk(db_session, user.id, document.id, CHUNK_CONTENT)
    create = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(document.id)]},
        headers=auth_cookie_headers(user.id),
    )
    conversation_id = create.json()["id"]

    _override_llm(responses=["factual_qa", "I like pizza and long walks on the beach."])
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": MATCHING_QUERY},
            headers=auth_cookie_headers(user.id),
        ) as response:
            events = await _parse_sse(response)
    finally:
        _clear_llm_override()

    full_text = "".join(
        data["text"] for name, data in events if name == "token"
    ).strip()
    assert "pizza" not in full_text
    assert "don't contain information relevant" in full_text
    citations_event = next(data for name, data in events if name == "citations")
    assert citations_event["citations"] == []


async def test_send_message_unknown_conversation_returns_404_before_stream(
    client, db_session
):
    user = await make_user(db_session)
    response = await client.post(
        f"/api/v1/chat/conversations/{uuid.uuid4()}/messages",
        json={"content": "hello"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404


async def test_send_message_cross_tenant_returns_404_before_stream(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(owner.id)
    )
    conversation_id = create.json()["id"]

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={"content": "hello"},
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


async def test_send_message_document_no_longer_ready_returns_409(client, db_session):
    from app.repositories.document_repository import DocumentRepository

    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    create = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(document.id)]},
        headers=auth_cookie_headers(user.id),
    )
    conversation_id = create.json()["id"]

    await DocumentRepository(db_session).set_status(
        user.id, document.id, status="failed", processing_error="reprocessing"
    )

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={"content": "hello"},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_not_ready"


async def test_send_message_empty_content_rejected(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={"content": ""},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422


async def test_send_message_too_long_content_rejected(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages",
        json={"content": "x" * 8001},
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 422

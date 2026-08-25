"""
tasks/remediation-plan.md R4 — testing.md §3.5's mandatory cross-tenant
category, applied specifically to chat's retrieval path: "the tenant check
happens before retrieval runs, not only at the HTTP routing layer."
"""

import json
import uuid

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.llm import FakeLLMProvider, get_llm_provider
from app.main import app
from app.models import Document, DocumentChunk
from tests.conftest import auth_cookie_headers, make_user

SHARED_CONTENT = "Quarterly revenue grew twelve percent year over year."
MATCHING_QUERY = "revenue grew twelve percent year over year"


def _override_llm(responses: list[str]):
    provider = FakeLLMProvider(responses=responses)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return provider


def _clear_llm_override() -> None:
    app.dependency_overrides.pop(get_llm_provider, None)


def _token_text(sse_body: bytes) -> str:
    """Concatenates every `event: token`'s `text` field from a raw SSE
    body — a multi-word phrase never appears contiguously in the raw
    bytes, since each word is its own separate `data:` line."""
    text = ""
    for block in sse_body.decode().split("\n\n"):
        lines = block.splitlines()
        if lines and lines[0] == "event: token":
            data_line = next(line for line in lines if line.startswith("data: "))
            text += json.loads(data_line[len("data: ") :])["text"]
    return text


async def _make_ready_document_with_chunk(db_session, user_id, *, content: str):
    document = Document(
        user_id=user_id,
        file_name="report.pdf",
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


async def test_workspace_chat_never_retrieves_another_users_documents(
    client, db_session
):
    """
    User A's workspace-scoped conversation (spans "all of the caller's
    ready documents") must never surface User B's chunk content as a
    citation, even though B's document has the exact same wording that
    would otherwise be a strong retrieval match.
    """
    victim = await make_user(db_session)
    attacker = await make_user(db_session)
    await _make_ready_document_with_chunk(db_session, victim.id, content=SHARED_CONTENT)

    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(attacker.id)
    )
    conversation_id = create.json()["id"]

    _override_llm(responses=["factual_qa"])
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": MATCHING_QUERY},
            headers=auth_cookie_headers(attacker.id),
        ) as response:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
    finally:
        _clear_llm_override()

    # No chunk exists for the attacker's own (empty) corpus -> graceful
    # decline, never the victim's content.
    full_text = _token_text(body)
    assert "Quarterly" not in full_text
    assert "don't contain information relevant" in full_text


async def test_multi_document_chat_scope_cannot_be_widened_to_another_users_document(
    client, db_session
):
    """A conversation explicitly scoped to the caller's own document cannot
    be tricked into retrieving a different user's document, even one with
    identical content — RetrievalService always filters by the
    authenticated user_id, never trusts a client-supplied scope alone."""
    victim = await make_user(db_session)
    attacker = await make_user(db_session)
    await _make_ready_document_with_chunk(db_session, victim.id, content=SHARED_CONTENT)
    attacker_document = await _make_ready_document_with_chunk(
        db_session, attacker.id, content="Completely unrelated attacker content."
    )

    create = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(attacker_document.id)]},
        headers=auth_cookie_headers(attacker.id),
    )
    conversation_id = create.json()["id"]

    _override_llm(responses=["factual_qa"])
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": MATCHING_QUERY},
            headers=auth_cookie_headers(attacker.id),
        ) as response:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
    finally:
        _clear_llm_override()

    assert "Quarterly" not in _token_text(body)


async def test_citation_never_references_another_users_document(client, db_session):
    """Direct citation-object-level check (testing.md §4.3), not just the
    HTTP-layer 404 pattern: a citation attached to User A's message can only
    ever point at User A's own document_id."""
    user = await make_user(db_session)
    other = await make_user(db_session)
    document = await _make_ready_document_with_chunk(
        db_session, user.id, content=SHARED_CONTENT
    )
    await _make_ready_document_with_chunk(db_session, other.id, content=SHARED_CONTENT)

    create = await client.post(
        "/api/v1/chat/conversations",
        json={"document_ids": [str(document.id)]},
        headers=auth_cookie_headers(user.id),
    )
    conversation_id = create.json()["id"]

    _override_llm(
        responses=["factual_qa", "Revenue grew twelve percent year over year."]
    )
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": MATCHING_QUERY},
            headers=auth_cookie_headers(user.id),
        ) as response:
            async for _ in response.aiter_text():
                pass
    finally:
        _clear_llm_override()

    detail = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(user.id),
    )
    citations = detail.json()["messages"][1]["citations"]
    assert len(citations) == 1
    assert citations[0]["document_id"] == str(document.id)


async def test_regenerate_cannot_be_used_to_reach_another_users_conversation(
    client, db_session
):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(owner.id)
    )
    conversation_id = create.json()["id"]

    _override_llm(responses=["out_of_scope"])
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "hi"},
            headers=auth_cookie_headers(owner.id),
        ) as response:
            async for _ in response.aiter_text():
                pass
    finally:
        _clear_llm_override()

    detail = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(owner.id),
    )
    assistant_message_id = detail.json()["messages"][1]["id"]

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages/{assistant_message_id}/regenerate",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404

"""tasks/remediation-plan.md R4 §7.1 — FR-AI-006 stop/regenerate."""

import uuid

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.llm import FakeLLMProvider, get_llm_provider
from app.core import chat_stream_control as stream_control
from app.main import app
from app.models import Document, DocumentChunk, Message
from app.repositories.conversation_repository import (
    CitationRepository,
    ConversationDocumentRepository,
    ConversationRepository,
    MessageRepository,
)
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.repositories.observability_repository import AiRequestRepository
from app.services.chat_service import ChatService
from app.services.retrieval_service import RetrievalService
from tests.conftest import auth_cookie_headers, make_user

CHUNK_CONTENT = "Quarterly revenue grew twelve percent year over year."
MATCHING_QUERY = "revenue grew twelve percent year over year"
# Long enough to give the stop-check loop multiple iterations, but built
# from words that genuinely overlap the seeded chunk (repeated) so the
# citation validator grounds it instead of falling back to NO_ANSWER_RESPONSE.
LONG_ANSWER = " ".join(["Revenue grew twelve percent year over year."] * 10)


def _override_llm(responses: list[str]):
    provider = FakeLLMProvider(responses=responses)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return provider


def _clear_llm_override() -> None:
    app.dependency_overrides.pop(get_llm_provider, None)


async def _make_service(db_session, llm) -> ChatService:
    embedding_provider = FakeEmbeddingProvider()
    return ChatService(
        ConversationRepository(db_session),
        ConversationDocumentRepository(db_session),
        MessageRepository(db_session),
        CitationRepository(db_session),
        DocumentRepository(db_session),
        AiRequestRepository(db_session),
        RetrievalService(
            DocumentChunkRepository(db_session),
            DocumentRepository(db_session),
            embedding_provider,
        ),
        llm,
    )


# --- stop (service-level: direct control over generator timing) ---


async def test_stop_mid_relay_persists_only_the_relayed_prefix(db_session):
    """
    Drives the async generator manually (not through the HTTP transport) so
    the test can call request_stop() itself between chunk yields — this is
    the only way to deterministically land "stop" mid-generation without
    racing real wall-clock timing against a fast in-memory fake provider.
    """
    user = await make_user(db_session)
    document = Document(
        user_id=user.id,
        file_name="report.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="ready",
    )
    db_session.add(document)
    await db_session.flush()
    embedding_provider = FakeEmbeddingProvider()
    [vector] = await embedding_provider.embed_batch([CHUNK_CONTENT])
    chunk = DocumentChunk(
        user_id=user.id,
        document_id=document.id,
        chunk_index=0,
        content=CHUNK_CONTENT,
        page_number=1,
        char_start=0,
        char_end=len(CHUNK_CONTENT),
        token_count=len(CHUNK_CONTENT.split()),
        embedding=vector,
        embedding_model=embedding_provider.model_name,
    )
    db_session.add(chunk)
    await db_session.flush()

    llm = FakeLLMProvider(responses=["factual_qa", LONG_ANSWER])
    service = await _make_service(db_session, llm)

    conversation = await ConversationRepository(db_session).create(
        user.id, scope_type="single_document", title=None
    )
    await ConversationDocumentRepository(db_session).add(conversation.id, document.id)
    conversation, user_message, document_ids = await service.prepare_message_turn(
        user.id, conversation.id, MATCHING_QUERY
    )

    generator = service.generate_turn_events(
        user.id, conversation, user_message, document_ids
    )
    events = []
    async for event in generator:
        events.append(event)
        if len(events) == 3:  # message_id + a couple of token events
            stopped = await stream_control.request_stop(user_message.id)
            assert stopped is True

    assert events[-1] not in events[:-1]  # sanity: loop actually advanced
    assert not any("done" in e for e in events)

    messages = await MessageRepository(db_session).list_for_conversation(
        user.id, conversation.id
    )
    assistant_message = next(m for m in messages if m.role == "assistant")
    assert assistant_message.status == "stopped"
    # Partial content is a strict prefix of the full answer, not the whole thing.
    assert assistant_message.content
    assert assistant_message.content.strip() != LONG_ANSWER.strip()
    assert LONG_ANSWER.startswith(assistant_message.content.strip())


async def test_stop_returns_409_when_nothing_in_progress(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]
    fake_message_id = uuid.uuid4()

    # Seed a user message directly (no turn ever started for it).
    message = Message(
        user_id=user.id,
        conversation_id=uuid.UUID(conversation_id),
        role="user",
        content="hi",
        status="complete",
    )
    message.id = fake_message_id
    db_session.add(message)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages/{fake_message_id}/stop",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_in_progress"


async def test_stop_unknown_message_returns_404(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages/{uuid.uuid4()}/stop",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404


async def test_stop_cross_tenant_returns_404(client, db_session):
    owner = await make_user(db_session)
    attacker = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(owner.id)
    )
    conversation_id = create.json()["id"]
    message = Message(
        user_id=owner.id,
        conversation_id=uuid.UUID(conversation_id),
        role="user",
        content="hi",
        status="complete",
    )
    db_session.add(message)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages/{message.id}/stop",
        headers=auth_cookie_headers(attacker.id),
    )
    assert response.status_code == 404


# --- regenerate ---


async def _make_ready_document(db_session, user_id):
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
    return document


async def test_regenerate_echoes_user_message_id_and_appends_new_assistant_row(
    client, db_session
):
    user = await make_user(db_session)
    document = await _make_ready_document(db_session, user.id)
    content = "Quarterly revenue grew twelve percent year over year."
    provider = FakeEmbeddingProvider()
    [vector] = await provider.embed_batch([content])
    chunk = DocumentChunk(
        user_id=user.id,
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
    db_session.add(chunk)
    await db_session.flush()

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
            json={"content": "revenue grew twelve percent year over year"},
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
    messages_before = detail.json()["messages"]
    assert len(messages_before) == 2
    user_message_id = messages_before[0]["id"]
    assistant_message_id = messages_before[1]["id"]

    _override_llm(
        responses=["factual_qa", "Revenue grew by twelve percent, year over year."]
    )
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages/{assistant_message_id}/regenerate",
            headers=auth_cookie_headers(user.id),
        ) as response:
            assert response.status_code == 200
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
    finally:
        _clear_llm_override()

    first_line = body.split(b"\n\n", 1)[0].decode()
    assert "event: message_id" in first_line
    import json as json_module

    data_line = next(
        line for line in first_line.splitlines() if line.startswith("data: ")
    )
    echoed_id = json_module.loads(data_line[len("data: ") :])["message_id"]
    assert echoed_id == user_message_id  # echoes the EXISTING user message id

    detail_after = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(user.id),
    )
    messages_after = detail_after.json()["messages"]
    assert len(messages_after) == 3  # appended, not edited in place
    assert messages_after[1]["id"] == assistant_message_id  # original untouched
    assert messages_after[2]["role"] == "assistant"
    assert messages_after[2]["id"] != assistant_message_id


async def test_regenerate_on_user_message_returns_404(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]
    message = Message(
        user_id=user.id,
        conversation_id=uuid.UUID(conversation_id),
        role="user",
        content="hi",
        status="complete",
    )
    db_session.add(message)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages/{message.id}/regenerate",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404


async def test_regenerate_with_no_preceding_user_message_returns_404(
    client, db_session
):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]
    # An orphan assistant message with no preceding user turn at all.
    message = Message(
        user_id=user.id,
        conversation_id=uuid.UUID(conversation_id),
        role="assistant",
        content="orphan",
        status="complete",
    )
    db_session.add(message)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages/{message.id}/regenerate",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404


async def test_regenerate_unknown_message_returns_404(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]

    response = await client.post(
        f"/api/v1/chat/conversations/{conversation_id}/messages/{uuid.uuid4()}/regenerate",
        headers=auth_cookie_headers(user.id),
    )
    assert response.status_code == 404

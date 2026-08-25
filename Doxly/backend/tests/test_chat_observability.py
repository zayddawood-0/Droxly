"""
tasks/remediation-plan.md R4 §7.2 — NFR-OBS-001 (P0): every chat turn writes
exactly one ai_requests row, success and failure paths alike, metadata-only.
"""

import uuid

from sqlalchemy import select

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.llm import FakeLLMProvider, get_llm_provider
from app.main import app
from app.models import AiRequest, Document, DocumentChunk
from tests.conftest import auth_cookie_headers, make_user

CHUNK_CONTENT = "Quarterly revenue grew twelve percent year over year."
MATCHING_QUERY = "revenue grew twelve percent year over year"
GROUNDED_ANSWER = "Revenue grew twelve percent year over year."


def _override_llm(responses=None, exception=None):
    provider = FakeLLMProvider(responses=responses or [])
    if exception is not None:

        async def _raising_generate(*args, **kwargs):
            raise exception

        provider.generate = _raising_generate  # type: ignore[method-assign]
    app.dependency_overrides[get_llm_provider] = lambda: provider
    return provider


def _clear_llm_override() -> None:
    app.dependency_overrides.pop(get_llm_provider, None)


async def _ai_requests_for(db_session, user_id) -> list[AiRequest]:
    result = await db_session.execute(
        select(AiRequest).where(AiRequest.user_id == user_id)
    )
    return list(result.scalars().all())


async def test_ai_requests_row_written_on_successful_turn(client, db_session):
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
    provider = FakeEmbeddingProvider()
    [vector] = await provider.embed_batch([CHUNK_CONTENT])
    db_session.add(
        DocumentChunk(
            user_id=user.id,
            document_id=document.id,
            chunk_index=0,
            content=CHUNK_CONTENT,
            page_number=1,
            char_start=0,
            char_end=len(CHUNK_CONTENT),
            token_count=len(CHUNK_CONTENT.split()),
            embedding=vector,
            embedding_model=provider.model_name,
        )
    )
    await db_session.flush()

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
            async for _ in response.aiter_text():
                pass
    finally:
        _clear_llm_override()

    rows = await _ai_requests_for(db_session, user.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.operation == "chat"
    assert row.provider == "fake"
    assert row.status == "success"
    assert row.error_code is None
    assert row.input_tokens is not None and row.input_tokens > 0
    assert row.output_tokens is not None and row.output_tokens > 0
    assert row.latency_ms is not None and row.latency_ms >= 0


async def test_ai_requests_row_written_on_out_of_scope_turn(client, db_session):
    """Even the cheap classifier-only path made a real provider call and gets logged."""
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]

    _override_llm(responses=["out_of_scope"])
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "hi there!"},
            headers=auth_cookie_headers(user.id),
        ) as response:
            async for _ in response.aiter_text():
                pass
    finally:
        _clear_llm_override()

    rows = await _ai_requests_for(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].operation == "chat"
    assert rows[0].status == "success"
    assert rows[0].model == "fake-fast"


async def test_ai_requests_row_written_on_failure(client, db_session):
    user = await make_user(db_session)
    create = await client.post(
        "/api/v1/chat/conversations", json={}, headers=auth_cookie_headers(user.id)
    )
    conversation_id = create.json()["id"]

    _override_llm(exception=RuntimeError("simulated provider outage"))
    try:
        async with client.stream(
            "POST",
            f"/api/v1/chat/conversations/{conversation_id}/messages",
            json={"content": "hello"},
            headers=auth_cookie_headers(user.id),
        ) as response:
            body = b""
            async for chunk in response.aiter_bytes():
                body += chunk
    finally:
        _clear_llm_override()

    assert b"event: error" in body
    assert b"generation_failed" in body
    assert b"simulated provider outage" not in body  # NFR-SEC-009 — sanitized

    rows = await _ai_requests_for(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].error_code == "generation_failed"

    # The incomplete assistant message is persisted, not discarded.
    detail = await client.get(
        f"/api/v1/chat/conversations/{conversation_id}",
        headers=auth_cookie_headers(user.id),
    )
    messages = detail.json()["messages"]
    assert len(messages) == 2
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == ""

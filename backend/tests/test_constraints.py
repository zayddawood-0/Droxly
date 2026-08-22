import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Citation, Comparison, Document, DocumentChunk, Tag, User


async def _make_user(session, email: str | None = None) -> User:
    user = User(
        email=email or f"{uuid.uuid4()}@example.com",
        display_name="Test User",
        password_hash="not-a-real-hash",
    )
    session.add(user)
    await session.flush()
    return user


async def _make_document(session, user: User) -> Document:
    doc = Document(
        user_id=user.id,
        file_name="test.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        status="ready",
    )
    session.add(doc)
    await session.flush()
    return doc


async def test_document_chunks_cascade_delete_with_document(db_session):
    """skills/database.md §8 — a chunk with no document is meaningless: CASCADE."""
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user)
    chunk = DocumentChunk(
        document_id=doc.id,
        user_id=user.id,
        chunk_index=0,
        content="hello",
        token_count=1,
    )
    db_session.add(chunk)
    await db_session.flush()

    await db_session.delete(doc)
    await db_session.flush()

    remaining = await db_session.execute(
        select(DocumentChunk).where(DocumentChunk.id == chunk.id)
    )
    assert remaining.scalar_one_or_none() is None


async def test_citation_survives_chunk_deletion_with_null_pointer(db_session):
    """
    specs/privacy.md §4 / skills/database.md §8 — citations.document_chunk_id
    is SET NULL, not CASCADE: a past chat citation's snippet survives even
    after its source chunk is purged, so conversation history stays coherent.
    """
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user)
    chunk = DocumentChunk(
        document_id=doc.id,
        user_id=user.id,
        chunk_index=0,
        content="hello",
        token_count=1,
    )
    db_session.add(chunk)
    await db_session.flush()

    from app.models import Conversation, Message

    conversation = Conversation(user_id=user.id, scope_type="single_document")
    db_session.add(conversation)
    await db_session.flush()
    message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role="assistant",
        content="Here's the answer.",
    )
    db_session.add(message)
    await db_session.flush()
    citation = Citation(
        message_id=message.id,
        document_chunk_id=chunk.id,
        document_id=doc.id,
        snippet="the relevant excerpt",
    )
    db_session.add(citation)
    await db_session.flush()
    citation_id = citation.id

    await db_session.delete(chunk)
    await db_session.flush()
    # ON DELETE SET NULL is a database-side effect the ORM's identity map
    # doesn't know about on its own — expire so the next query re-reads
    # citation's actual current row instead of returning the cached object.
    db_session.expire_all()

    result = await db_session.execute(
        select(Citation).where(Citation.id == citation_id)
    )
    surviving = result.scalar_one()
    assert surviving.document_chunk_id is None
    assert surviving.snippet == "the relevant excerpt"


async def test_comparisons_check_constraint_rejects_identical_documents(db_session):
    """FR-COMP-001 acceptance criteria / database.md §3.12 CHECK constraint."""
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user)

    db_session.add(
        Comparison(
            user_id=user.id,
            document_a_id=doc.id,
            document_b_id=doc.id,
            result_json={},
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_users_email_unique_constraint(db_session):
    email = f"{uuid.uuid4()}@example.com"
    await _make_user(db_session, email=email)
    db_session.add(User(email=email, display_name="Duplicate"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_tags_unique_per_user_not_globally(db_session):
    """UNIQUE(user_id, name) — same tag name is fine across different users."""
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)

    db_session.add(Tag(user_id=user_a.id, name="invoices"))
    db_session.add(Tag(user_id=user_b.id, name="invoices"))
    await db_session.flush()  # no error — different owners

    db_session.add(Tag(user_id=user_a.id, name="invoices"))
    with pytest.raises(IntegrityError):
        await db_session.flush()

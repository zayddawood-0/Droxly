import uuid

from app.ai.embeddings import FakeEmbeddingProvider
from app.models import Document, User
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)

_provider = FakeEmbeddingProvider()


async def _make_user(session, email: str | None = None) -> User:
    user = User(
        email=email or f"{uuid.uuid4()}@example.com",
        display_name="Test User",
        password_hash="not-a-real-hash",
    )
    session.add(user)
    await session.flush()
    return user


async def _make_document(
    session, user_id: uuid.UUID, *, status: str = "embedding"
) -> Document:
    document = Document(
        user_id=user_id,
        file_name="report.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        status=status,
    )
    session.add(document)
    await session.flush()
    return document


async def _insert_chunks(
    chunk_repo: DocumentChunkRepository,
    user_id: uuid.UUID,
    document_id: uuid.UUID,
    texts: list[str],
) -> None:
    vectors = await _provider.embed_batch(texts)
    await chunk_repo.bulk_create(
        user_id,
        document_id,
        [
            {
                "chunk_index": i,
                "content": text,
                "page_number": None,
                "char_start": 0,
                "char_end": len(text),
                "token_count": len(text.split()),
                "embedding": vector,
                "embedding_model": _provider.model_name,
            }
            for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
        ],
    )


async def test_bulk_create_denormalizes_user_id_onto_every_chunk(db_session):
    """database.md §3.4's note: user_id is kept in sync at insert time — this is what makes the join-free tenant filter in similarity_search correct."""
    user = await _make_user(db_session)
    document = await _make_document(db_session, user.id)
    chunk_repo = DocumentChunkRepository(db_session)

    await _insert_chunks(
        chunk_repo, user.id, document.id, ["chunk one text", "chunk two text"]
    )

    rows = await chunk_repo.list(user.id)
    assert len(rows) == 2
    assert all(row.user_id == user.id for row in rows)
    assert all(row.document_id == document.id for row in rows)


async def test_similarity_search_ranks_more_relevant_chunks_first(db_session):
    """rag.md §6 — ORDER BY cosine distance ascending == similarity descending."""
    user = await _make_user(db_session)
    document = await _make_document(db_session, user.id)
    chunk_repo = DocumentChunkRepository(db_session)

    await _insert_chunks(
        chunk_repo,
        user.id,
        document.id,
        [
            "quarterly financial report revenue and growth figures",
            "a recipe for chocolate chip cookies and baking tips",
        ],
    )

    [query_vector] = await _provider.embed_batch(
        ["annual financial report revenue summary"]
    )
    results = await chunk_repo.similarity_search(
        user.id, query_vector, min_similarity=-1.0
    )

    assert len(results) == 2
    assert "financial" in results[0].chunk.content
    assert results[0].similarity > results[1].similarity


async def test_similarity_search_never_returns_another_user_s_chunks(db_session):
    """Mandatory cross-tenant isolation test (testing.md §4 — the RAG-layer instance of the mandatory category)."""
    owner = await _make_user(db_session)
    other_user = await _make_user(db_session)
    owner_doc = await _make_document(db_session, owner.id)
    other_doc = await _make_document(db_session, other_user.id)
    chunk_repo = DocumentChunkRepository(db_session)

    await _insert_chunks(
        chunk_repo, owner.id, owner_doc.id, ["owner's private financial data"]
    )
    await _insert_chunks(
        chunk_repo, other_user.id, other_doc.id, ["other user's private financial data"]
    )

    [query_vector] = await _provider.embed_batch(["private financial data"])
    results = await chunk_repo.similarity_search(
        other_user.id, query_vector, min_similarity=-1.0
    )

    assert len(results) == 1
    assert results[0].chunk.document_id == other_doc.id
    assert results[0].chunk.user_id == other_user.id


async def test_similarity_search_respects_the_relevance_threshold(db_session):
    """rag.md §6 — results below the configured floor never reach the caller."""
    user = await _make_user(db_session)
    document = await _make_document(db_session, user.id)
    chunk_repo = DocumentChunkRepository(db_session)

    await _insert_chunks(
        chunk_repo, user.id, document.id, ["completely unrelated cooking content"]
    )

    [query_vector] = await _provider.embed_batch(["quarterly financial revenue growth"])
    results = await chunk_repo.similarity_search(
        user.id, query_vector, min_similarity=0.99
    )

    assert results == []


async def test_similarity_search_can_be_scoped_to_a_single_document(db_session):
    user = await _make_user(db_session)
    doc_a = await _make_document(db_session, user.id)
    doc_b = await _make_document(db_session, user.id)
    chunk_repo = DocumentChunkRepository(db_session)

    await _insert_chunks(chunk_repo, user.id, doc_a.id, ["financial report content"])
    await _insert_chunks(chunk_repo, user.id, doc_b.id, ["financial report content"])

    [query_vector] = await _provider.embed_batch(["financial report"])
    results = await chunk_repo.similarity_search(
        user.id, query_vector, document_id=doc_a.id, min_similarity=-1.0
    )

    assert len(results) == 1
    assert results[0].chunk.document_id == doc_a.id


async def test_similarity_search_respects_k_limit(db_session):
    user = await _make_user(db_session)
    document = await _make_document(db_session, user.id)
    chunk_repo = DocumentChunkRepository(db_session)

    await _insert_chunks(
        chunk_repo,
        user.id,
        document.id,
        [f"financial report section {i} revenue details" for i in range(5)],
    )

    [query_vector] = await _provider.embed_batch(["financial report revenue"])
    results = await chunk_repo.similarity_search(
        user.id, query_vector, k=2, min_similarity=-1.0
    )

    assert len(results) == 2


async def test_set_status_is_owner_scoped(db_session):
    owner = await _make_user(db_session)
    other_user = await _make_user(db_session)
    document = await _make_document(db_session, owner.id, status="embedding")
    doc_repo = DocumentRepository(db_session)

    unauthorized = await doc_repo.set_status(other_user.id, document.id, status="ready")
    assert unauthorized is None

    updated = await doc_repo.set_status(owner.id, document.id, status="ready")
    assert updated is not None
    assert updated.status == "ready"

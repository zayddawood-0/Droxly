"""
rag.md §12 (Hybrid Search) — tasks/remediation-plan.md R8. Repository-level
coverage of SearchRepository's fused ranking/filtering query, independent of
the HTTP layer (test_search_api.py covers the full request/response
contract). Uses the same real-Postgres, FakeEmbeddingProvider pattern
test_retrieval_service.py already established.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.ai.embeddings import FakeEmbeddingProvider
from app.models import Document, DocumentTag, Tag, User
from app.repositories.document_repository import DocumentChunkRepository
from app.repositories.search_repository import SearchRepository

_provider = FakeEmbeddingProvider()


async def _make_user(session) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Test User",
        password_hash="not-a-real-hash",
    )
    session.add(user)
    await session.flush()
    return user


async def _make_document(
    session,
    user_id: uuid.UUID,
    *,
    file_name: str = "report.pdf",
    mime_type: str = "application/pdf",
    status: str = "ready",
    created_at=None,
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
    session.add(document)
    await session.flush()
    if created_at is not None:
        document.created_at = created_at
        await session.flush()
    return document


async def _insert_chunk(
    session, user_id, document_id, content: str, *, page_number: int = 1
) -> None:
    [vector] = await _provider.embed_batch([content])
    await DocumentChunkRepository(session).bulk_create(
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


def _repo(session) -> SearchRepository:
    return SearchRepository(session)


async def _embed_query(text: str) -> list[float]:
    # A real (non-zero) embedding — pgvector's cosine_distance is undefined
    # for a zero vector, so tests must embed the query the same way
    # SearchService does, not hand it an arbitrary placeholder vector.
    [vector] = await _provider.embed_batch([text])
    return vector


async def test_search_finds_exact_keyword_match_via_content(db_session):
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user.id, file_name="report.pdf")
    await _insert_chunk(
        db_session, user.id, doc.id, "quarterly revenue and growth figures"
    )

    hits, total = await _repo(db_session).search(
        user.id,
        "quarterly revenue",
        await _embed_query("quarterly revenue"),
        limit=20,
        offset=0,
    )

    assert total == 1
    assert hits[0].document_id == doc.id
    assert hits[0].page_number == 1
    assert hits[0].relevance_score > 0


async def test_search_finds_filename_matches_with_no_page(db_session):
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user.id, file_name="invoice-march.pdf")
    await _insert_chunk(db_session, user.id, doc.id, "unrelated content entirely")

    hits, total = await _repo(db_session).search(
        user.id, "invoice", await _embed_query("invoice"), limit=20, offset=0
    )

    assert total == 1
    assert hits[0].document_id == doc.id
    assert hits[0].page_number is None
    assert hits[0].content == "invoice-march.pdf"


async def test_search_is_scoped_to_the_requesting_user(db_session):
    owner = await _make_user(db_session)
    attacker = await _make_user(db_session)
    doc = await _make_document(db_session, owner.id, file_name="secret-plan.pdf")
    await _insert_chunk(db_session, owner.id, doc.id, "confidential merger details")

    hits, total = await _repo(db_session).search(
        attacker.id,
        "confidential merger",
        await _embed_query("confidential merger"),
        limit=20,
        offset=0,
    )

    assert total == 0
    assert hits == []


async def test_search_excludes_soft_deleted_documents(db_session):
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user.id, file_name="old.pdf")
    await _insert_chunk(db_session, user.id, doc.id, "archived project notes")
    doc.deleted_at = datetime.now(UTC)
    await db_session.flush()

    hits, total = await _repo(db_session).search(
        user.id,
        "archived project",
        await _embed_query("archived project"),
        limit=20,
        offset=0,
    )

    assert total == 0
    assert hits == []


async def test_search_returns_empty_for_no_match(db_session):
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user.id)
    await _insert_chunk(db_session, user.id, doc.id, "completely unrelated wording")

    hits, total = await _repo(db_session).search(
        user.id,
        "xyzzy nonexistent term",
        await _embed_query("xyzzy nonexistent term"),
        limit=20,
        offset=0,
    )

    assert total == 0
    assert hits == []


async def test_search_filters_by_mime_type(db_session):
    user = await _make_user(db_session)
    pdf_doc = await _make_document(
        db_session, user.id, file_name="a.pdf", mime_type="application/pdf"
    )
    txt_doc = await _make_document(
        db_session, user.id, file_name="b.txt", mime_type="text/plain"
    )
    await _insert_chunk(db_session, user.id, pdf_doc.id, "budget forecast numbers")
    await _insert_chunk(db_session, user.id, txt_doc.id, "budget forecast numbers")

    hits, total = await _repo(db_session).search(
        user.id,
        "budget forecast",
        await _embed_query("budget forecast"),
        limit=20,
        offset=0,
        mime_type="text/plain",
    )

    assert total == 1
    assert hits[0].document_id == txt_doc.id


async def test_search_filters_by_status(db_session):
    user = await _make_user(db_session)
    ready_doc = await _make_document(db_session, user.id, status="ready")
    queued_doc = await _make_document(db_session, user.id, status="queued")
    await _insert_chunk(db_session, user.id, ready_doc.id, "onboarding checklist steps")
    # A queued document has no real chunks yet in production, but filename
    # search must still respect an explicit status filter when supplied.
    queued_doc.file_name = "onboarding-checklist.pdf"
    await db_session.flush()

    hits, total = await _repo(db_session).search(
        user.id,
        "onboarding checklist",
        await _embed_query("onboarding checklist"),
        limit=20,
        offset=0,
        status="queued",
    )

    assert total == 1
    assert hits[0].document_id == queued_doc.id


async def test_search_filters_by_tag(db_session):
    user = await _make_user(db_session)
    tagged_doc = await _make_document(db_session, user.id, file_name="tagged.pdf")
    other_doc = await _make_document(db_session, user.id, file_name="other.pdf")
    tag = Tag(user_id=user.id, name="finance")
    db_session.add(tag)
    await db_session.flush()
    db_session.add(DocumentTag(document_id=tagged_doc.id, tag_id=tag.id))
    await db_session.flush()
    await _insert_chunk(db_session, user.id, tagged_doc.id, "expense report totals")
    await _insert_chunk(db_session, user.id, other_doc.id, "expense report totals")

    hits, total = await _repo(db_session).search(
        user.id,
        "expense report",
        await _embed_query("expense report"),
        limit=20,
        offset=0,
        tag_id=tag.id,
    )

    assert total == 1
    assert hits[0].document_id == tagged_doc.id


async def test_search_filters_by_date_range(db_session):
    today = datetime.now(UTC).date()
    user = await _make_user(db_session)
    old_doc = await _make_document(
        db_session,
        user.id,
        file_name="old.pdf",
        created_at=today - timedelta(days=30),
    )
    recent_doc = await _make_document(db_session, user.id, file_name="recent.pdf")
    await _insert_chunk(db_session, user.id, old_doc.id, "milestone tracking summary")
    await _insert_chunk(
        db_session, user.id, recent_doc.id, "milestone tracking summary"
    )

    hits, total = await _repo(db_session).search(
        user.id,
        "milestone tracking",
        await _embed_query("milestone tracking"),
        limit=20,
        offset=0,
        date_from=today - timedelta(days=1),
    )

    assert total == 1
    assert hits[0].document_id == recent_doc.id


async def test_search_pagination_and_deterministic_ordering(db_session):
    user = await _make_user(db_session)
    doc = await _make_document(db_session, user.id)
    for i in range(5):
        await DocumentChunkRepository(db_session).bulk_create(
            user.id,
            doc.id,
            [
                {
                    "chunk_index": i + 1,
                    "content": f"annual compliance audit section {i}",
                    "page_number": i + 1,
                    "char_start": 0,
                    "char_end": 10,
                    "token_count": 5,
                    "embedding": (await _provider.embed_batch(["x"]))[0],
                    "embedding_model": _provider.model_name,
                }
            ],
        )

    first_page, total = await _repo(db_session).search(
        user.id,
        "annual compliance audit",
        await _embed_query("annual compliance audit"),
        limit=2,
        offset=0,
    )
    second_page, _ = await _repo(db_session).search(
        user.id,
        "annual compliance audit",
        await _embed_query("annual compliance audit"),
        limit=2,
        offset=2,
    )
    repeat_first_page, _ = await _repo(db_session).search(
        user.id,
        "annual compliance audit",
        await _embed_query("annual compliance audit"),
        limit=2,
        offset=0,
    )

    assert total == 5
    assert len(first_page) == 2
    assert len(second_page) == 2
    assert [h.content for h in first_page] == [h.content for h in repeat_first_page]
    first_ids = {h.content for h in first_page}
    second_ids = {h.content for h in second_page}
    assert first_ids.isdisjoint(second_ids)

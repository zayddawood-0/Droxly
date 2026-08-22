import uuid

from app.ai.embeddings import FakeEmbeddingProvider
from app.models import Document, User
from app.repositories.document_repository import (
    DocumentChunkRepository,
    DocumentRepository,
)
from app.services.retrieval_service import (
    MULTI_DOCUMENT_K,
    SINGLE_DOCUMENT_K,
    RetrievalService,
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
    session, user_id: uuid.UUID, file_name: str = "report.pdf"
) -> Document:
    document = Document(
        user_id=user_id,
        file_name=file_name,
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=1024,
        checksum_sha256="a" * 64,
        status="embedding",
    )
    session.add(document)
    await session.flush()
    return document


async def _insert_chunks(chunk_repo, user_id, document_id, texts: list[str]) -> None:
    vectors = await _provider.embed_batch(texts)
    await chunk_repo.bulk_create(
        user_id,
        document_id,
        [
            {
                "chunk_index": i,
                "content": text,
                "page_number": i + 1,
                "char_start": 0,
                "char_end": len(text),
                "token_count": len(text.split()),
                "embedding": vector,
                "embedding_model": _provider.model_name,
            }
            for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
        ],
    )


def _make_service(session) -> RetrievalService:
    return RetrievalService(
        DocumentChunkRepository(session), DocumentRepository(session), _provider
    )


async def test_retrieve_returns_assembled_context_with_provenance(db_session):
    user = await _make_user(db_session)
    document = await _make_document(
        db_session, user.id, file_name="quarterly-report.pdf"
    )
    await _insert_chunks(
        DocumentChunkRepository(db_session),
        user.id,
        document.id,
        ["quarterly financial revenue and growth figures"],
    )
    service = _make_service(db_session)

    context = await service.retrieve(
        user.id, "quarterly revenue growth", min_similarity=-1.0
    )

    assert not context.is_empty
    item = context.items[0]
    assert item.document_id == document.id
    assert item.document_title == "quarterly-report.pdf"
    assert item.page_number == 1
    assert item.token_count > 0
    assert context.total_tokens == sum(i.token_count for i in context.items)


async def test_retrieve_with_no_matching_chunks_returns_empty_context(db_session):
    """FR-RAG-003 — a success-path empty result, not an exception."""
    user = await _make_user(db_session)
    document = await _make_document(db_session, user.id)
    await _insert_chunks(
        DocumentChunkRepository(db_session),
        user.id,
        document.id,
        ["a recipe for chocolate chip cookies"],
    )
    service = _make_service(db_session)

    context = await service.retrieve(
        user.id, "quarterly financial revenue growth", min_similarity=0.99
    )

    assert context.is_empty
    assert context.items == []
    assert context.total_tokens == 0


async def test_retrieve_never_returns_another_users_chunks(db_session):
    """Mandatory cross-tenant isolation, asserted at the service level too (testing.md §4.2 — retrieval sits behind an LLM call, a leak is harder to notice)."""
    owner = await _make_user(db_session)
    other_user = await _make_user(db_session)
    owner_doc = await _make_document(db_session, owner.id)
    other_doc = await _make_document(db_session, other_user.id)
    chunk_repo = DocumentChunkRepository(db_session)
    await _insert_chunks(chunk_repo, owner.id, owner_doc.id, ["owner's private data"])
    await _insert_chunks(
        chunk_repo, other_user.id, other_doc.id, ["other user's private data"]
    )

    service = _make_service(db_session)
    context = await service.retrieve(other_user.id, "private data", min_similarity=-1.0)

    assert all(item.document_id == other_doc.id for item in context.items)


async def test_retrieve_dedupes_near_identical_chunks(db_session):
    """rag.md §8 point 1."""
    user = await _make_user(db_session)
    document = await _make_document(db_session, user.id)
    base = "The quarterly financial report shows strong revenue growth this year"
    await _insert_chunks(
        DocumentChunkRepository(db_session),
        user.id,
        document.id,
        [base, base + "."],  # near-identical, trivially >90% overlap
    )
    service = _make_service(db_session)

    context = await service.retrieve(
        user.id, "quarterly revenue growth", min_similarity=-1.0
    )

    assert len(context.items) == 1


async def test_retrieve_trims_to_a_small_token_budget(db_session):
    """rag.md §8 point 3."""
    user = await _make_user(db_session)
    document = await _make_document(db_session, user.id)
    texts = [
        f"financial report section {i} revenue details and figures" for i in range(6)
    ]
    await _insert_chunks(
        DocumentChunkRepository(db_session), user.id, document.id, texts
    )
    service = _make_service(db_session)

    context = await service.retrieve(
        user.id, "financial report revenue", token_budget=20, min_similarity=-1.0
    )

    assert len(context.items) < 6
    assert context.total_tokens <= 20 or len(context.items) == 1


# Deliberately unrelated-to-each-other sentences (not "topic {i}" variants,
# which SequenceMatcher rates >90% similar to one another and would collapse
# under dedup, defeating these tests' point of isolating the k-limit alone).
_DISTINCT_FINANCIAL_SENTENCES = [
    "Revenue from product sales increased across all regions this quarter.",
    "Operating expenses were reduced through supply chain renegotiation.",
    "The board approved a new capital allocation strategy for expansion.",
    "Customer acquisition costs dropped due to improved marketing efficiency.",
    "Debt refinancing lowered the company's average interest rate significantly.",
    "Inventory turnover improved following the warehouse automation rollout.",
    "Gross margin expanded thanks to favorable commodity pricing trends.",
    "The subsidiary in Europe reported its first profitable fiscal year.",
    "Employee headcount grew modestly while productivity metrics rose sharply.",
    "Cash reserves were bolstered by a successful secondary stock offering.",
    "Litigation settlements were resolved below the previously reserved amount.",
    "The new product line contributed meaningfully to overall unit economics.",
    "Currency headwinds partially offset otherwise strong regional performance.",
    "Research spending increased to accelerate the next-generation platform.",
    "Shareholder returns benefited from an expanded stock buyback program.",
]


async def test_single_document_scope_uses_the_narrower_k(db_session):
    user = await _make_user(db_session)
    document = await _make_document(db_session, user.id)
    await _insert_chunks(
        DocumentChunkRepository(db_session),
        user.id,
        document.id,
        _DISTINCT_FINANCIAL_SENTENCES,
    )
    service = _make_service(db_session)

    context = await service.retrieve(
        user.id, "financial revenue", document_id=document.id, min_similarity=-1.0
    )

    assert len(context.items) <= SINGLE_DOCUMENT_K


async def test_multi_document_scope_uses_the_wider_k(db_session):
    user = await _make_user(db_session)
    chunk_repo = DocumentChunkRepository(db_session)
    doc_ids = []
    for i, sentence in enumerate(_DISTINCT_FINANCIAL_SENTENCES):
        document = await _make_document(db_session, user.id, file_name=f"doc-{i}.pdf")
        doc_ids.append(document.id)
        await _insert_chunks(chunk_repo, user.id, document.id, [sentence])
    service = _make_service(db_session)

    context = await service.retrieve(
        user.id, "financial revenue", document_ids=doc_ids, min_similarity=-1.0
    )

    assert len(context.items) <= MULTI_DOCUMENT_K
    assert len(context.items) > SINGLE_DOCUMENT_K

import uuid

import pytest

from app.ai.embeddings import FakeEmbeddingProvider
from app.errors import EmptyDocumentError
from app.services.embedding_service import EmbeddingService


class _FakeChunkRepository:
    """
    skills/backend.md §3 — a service must be unit-testable "with its
    repositories mocked/faked", independent of a real database. This fake
    stands in for DocumentChunkRepository, recording exactly what the
    service tried to persist.
    """

    def __init__(self) -> None:
        self.created: list[dict] = []

    async def bulk_create(self, user_id, document_id, chunks):
        self.created.extend(chunks)
        return chunks


class _FakeDocumentRepository:
    def __init__(self) -> None:
        self.status_calls: list[tuple] = []

    async def set_status(self, user_id, document_id, *, status, processing_error=None):
        self.status_calls.append((user_id, document_id, status, processing_error))


@pytest.fixture
def service():
    chunk_repo = _FakeChunkRepository()
    document_repo = _FakeDocumentRepository()
    embedding_service = EmbeddingService(
        chunk_repo, document_repo, FakeEmbeddingProvider()
    )
    return embedding_service, chunk_repo, document_repo


async def test_process_extracted_text_creates_chunks_and_marks_the_document_ready(
    service,
):
    embedding_service, chunk_repo, document_repo = service
    user_id, document_id = uuid.uuid4(), uuid.uuid4()
    text = ("A meaningful paragraph about testing. " * 30).strip()

    count = await embedding_service.process_extracted_text(user_id, document_id, text)

    assert count > 0
    assert len(chunk_repo.created) == count
    assert all(
        "embedding" in chunk and chunk["embedding"] is not None
        for chunk in chunk_repo.created
    )
    assert all(
        chunk["embedding_model"] == "fake-hashing-v1" for chunk in chunk_repo.created
    )
    assert document_repo.status_calls == [(user_id, document_id, "ready", None)]


async def test_process_extracted_text_raises_on_degenerate_input_and_never_marks_ready(
    service,
):
    """rag.md §2 / FR-PROC-004 — a document with no extractable text is never silently marked ready."""
    embedding_service, chunk_repo, document_repo = service
    user_id, document_id = uuid.uuid4(), uuid.uuid4()

    with pytest.raises(EmptyDocumentError) as exc_info:
        await embedding_service.process_extracted_text(user_id, document_id, "   ")

    assert exc_info.value.document_id == document_id
    assert chunk_repo.created == []
    assert document_repo.status_calls == []


async def test_chunk_order_is_preserved_through_embedding_and_persistence(service):
    embedding_service, chunk_repo, _ = service
    user_id, document_id = uuid.uuid4(), uuid.uuid4()
    text = "\n\n".join(
        f"Paragraph {i} with distinct content about topic {i}." for i in range(10)
    )

    await embedding_service.process_extracted_text(user_id, document_id, text)

    assert [chunk["chunk_index"] for chunk in chunk_repo.created] == list(
        range(len(chunk_repo.created))
    )

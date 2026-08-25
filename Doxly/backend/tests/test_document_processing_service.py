"""
tasks/remediation-plan.md R3 — DocumentProcessingService, repositories/
storage/embedding provider faked (skills/backend.md §3.1's service-unit-test
shape: business logic, no database).
"""

import uuid
from dataclasses import dataclass, field

import pytest

from app.ai.embeddings import FakeEmbeddingProvider
from app.document_processing.base import (
    CorruptFileError,
    DocumentParser,
    ParsedCsv,
    ParsedText,
    TransientParseError,
)
from app.services.document_processing_service import DocumentProcessingService


@dataclass
class _FakeDocument:
    id: uuid.UUID
    storage_key: str
    mime_type: str
    status: str
    page_count: int | None = None
    extracted_text_available: bool = False


class _FakeSession:
    def __init__(self) -> None:
        self.flush_count = 0

    async def flush(self) -> None:
        self.flush_count += 1


class _FakeDocumentRepository:
    def __init__(self, document: _FakeDocument | None) -> None:
        self._document = document
        self.status_calls: list[tuple] = []
        self.session = _FakeSession()

    async def get(self, user_id, document_id):
        return self._document

    async def set_status(self, user_id, document_id, *, status, processing_error=None):
        self.status_calls.append((status, processing_error))
        if self._document is not None:
            self._document.status = status
        return self._document


class _FakeChunkRepository:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.deleted_calls = 0

    async def delete_for_document(self, user_id, document_id) -> int:
        self.deleted_calls += 1
        count = len(self.created)
        self.created = []
        return count

    async def bulk_create(self, user_id, document_id, chunks):
        self.created.extend(chunks)
        return chunks


class _FakeStorageProvider:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read_object_bytes(self, key: str) -> bytes:
        return self._data


@dataclass
class _FakeParser(DocumentParser):
    mime_type: str = "application/pdf"
    result: object = None
    error: Exception | None = None
    sniff_result: bool = True
    calls: list = field(default_factory=list)

    def sniff_matches(self, header_bytes: bytes) -> bool:
        return self.sniff_result

    def parse(self, data: bytes):
        self.calls.append(data)
        if self.error is not None:
            raise self.error
        return self.result


def _install_fake_parser(monkeypatch, parser: _FakeParser) -> None:
    import app.services.document_processing_service as svc_module

    monkeypatch.setattr(svc_module, "get_parser", lambda mime_type: parser)


@pytest.fixture
def embedding_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


async def test_successful_pipeline_transitions_through_every_stage_in_order(
    monkeypatch, embedding_provider
):
    document = _FakeDocument(
        id=uuid.uuid4(), storage_key="k", mime_type="application/pdf", status="queued"
    )
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    parser = _FakeParser(
        result=ParsedText(
            full_text="A meaningful paragraph about testing. " * 30,
            page_breaks=None,
            page_count=3,
        )
    )
    _install_fake_parser(monkeypatch, parser)

    service = DocumentProcessingService(
        document_repo,
        chunk_repo,
        _FakeStorageProvider(b"%PDF-fake"),
        embedding_provider,
    )

    await service.process_document(document.id, document.id)

    assert [status for status, _ in document_repo.status_calls] == [
        "extracting",
        "chunking",
        "embedding",
        "ready",
    ]
    assert len(chunk_repo.created) > 0
    assert document.page_count == 3
    assert document.extracted_text_available is True


async def test_permanent_parse_failure_marks_failed_without_raising(
    monkeypatch, embedding_provider
):
    document = _FakeDocument(
        id=uuid.uuid4(), storage_key="k", mime_type="application/pdf", status="queued"
    )
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    parser = _FakeParser(error=CorruptFileError())
    _install_fake_parser(monkeypatch, parser)

    service = DocumentProcessingService(
        document_repo,
        chunk_repo,
        _FakeStorageProvider(b"%PDF-fake"),
        embedding_provider,
    )

    await service.process_document(document.id, document.id)  # must not raise

    statuses = [status for status, _ in document_repo.status_calls]
    assert statuses[-1] == "failed"
    assert document_repo.status_calls[-1][1] == CorruptFileError().user_message
    assert chunk_repo.created == []


async def test_transient_failure_propagates_and_does_not_mark_failed(
    monkeypatch, embedding_provider
):
    """
    NFR-AVAIL-002 — a transient failure is the caller's (worker's) job to
    retry; the service itself never writes a terminal `failed` status for
    it (that would prevent a subsequent retry from proceeding cleanly).
    """
    document = _FakeDocument(
        id=uuid.uuid4(), storage_key="k", mime_type="application/pdf", status="queued"
    )
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    parser = _FakeParser(error=TransientParseError())
    _install_fake_parser(monkeypatch, parser)

    service = DocumentProcessingService(
        document_repo,
        chunk_repo,
        _FakeStorageProvider(b"%PDF-fake"),
        embedding_provider,
    )

    with pytest.raises(TransientParseError):
        await service.process_document(document.id, document.id)

    assert "failed" not in [status for status, _ in document_repo.status_calls]


async def test_degenerate_extraction_yields_empty_document_error_and_marks_failed(
    monkeypatch, embedding_provider
):
    document = _FakeDocument(
        id=uuid.uuid4(), storage_key="k", mime_type="text/plain", status="queued"
    )
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    parser = _FakeParser(
        mime_type="text/plain",
        result=ParsedText(full_text="   ", page_breaks=None, page_count=None),
    )
    _install_fake_parser(monkeypatch, parser)

    service = DocumentProcessingService(
        document_repo,
        chunk_repo,
        _FakeStorageProvider(b"whitespace"),
        embedding_provider,
    )

    await service.process_document(document.id, document.id)

    assert document_repo.status_calls[-1][0] == "failed"
    assert chunk_repo.created == []


async def test_csv_parsed_document_uses_row_group_chunking(
    monkeypatch, embedding_provider
):
    document = _FakeDocument(
        id=uuid.uuid4(), storage_key="k", mime_type="text/csv", status="queued"
    )
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    parser = _FakeParser(
        mime_type="text/csv",
        result=ParsedCsv(
            header=["name", "score"],
            rows=[{"name": "Alice", "score": "95"}, {"name": "Bob", "score": "88"}],
        ),
    )
    _install_fake_parser(monkeypatch, parser)

    service = DocumentProcessingService(
        document_repo,
        chunk_repo,
        _FakeStorageProvider(b"name,score"),
        embedding_provider,
    )

    await service.process_document(document.id, document.id)

    assert document.status == "ready"
    assert len(chunk_repo.created) == 1
    assert "name,score" in chunk_repo.created[0]["content"]
    assert chunk_repo.created[0]["page_number"] is None


async def test_already_ready_document_is_a_no_op(monkeypatch, embedding_provider):
    document = _FakeDocument(
        id=uuid.uuid4(), storage_key="k", mime_type="application/pdf", status="ready"
    )
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    parser = _FakeParser()
    _install_fake_parser(monkeypatch, parser)

    service = DocumentProcessingService(
        document_repo,
        chunk_repo,
        _FakeStorageProvider(b"%PDF-fake"),
        embedding_provider,
    )

    await service.process_document(document.id, document.id)

    assert document_repo.status_calls == []
    assert parser.calls == []


async def test_missing_document_is_silently_skipped(monkeypatch, embedding_provider):
    document_repo = _FakeDocumentRepository(None)
    chunk_repo = _FakeChunkRepository()
    parser = _FakeParser()
    _install_fake_parser(monkeypatch, parser)

    service = DocumentProcessingService(
        document_repo,
        chunk_repo,
        _FakeStorageProvider(b"%PDF-fake"),
        embedding_provider,
    )

    await service.process_document(uuid.uuid4(), uuid.uuid4())  # must not raise

    assert document_repo.status_calls == []


async def test_retry_after_partial_failure_clears_prior_chunks_before_rewriting(
    monkeypatch, embedding_provider
):
    """
    NFR-AVAIL-002/FR-PROC-005 idempotency — simulates a document that
    already has chunks from a prior, incomplete attempt (left `embedding`
    by a crash before the terminal status write); a fresh run clears them
    before writing the new set rather than appending.
    """
    document = _FakeDocument(
        id=uuid.uuid4(),
        storage_key="k",
        mime_type="application/pdf",
        status="embedding",
    )
    document_repo = _FakeDocumentRepository(document)
    chunk_repo = _FakeChunkRepository()
    chunk_repo.created = [
        {"chunk_index": 0, "content": "stale chunk from a prior attempt"}
    ]
    parser = _FakeParser(
        result=ParsedText(
            full_text="Fresh content after a retry. " * 30,
            page_breaks=None,
            page_count=None,
        )
    )
    _install_fake_parser(monkeypatch, parser)

    service = DocumentProcessingService(
        document_repo,
        chunk_repo,
        _FakeStorageProvider(b"%PDF-fake"),
        embedding_provider,
    )

    await service.process_document(document.id, document.id)

    assert chunk_repo.deleted_calls == 1
    assert all("stale chunk" not in c["content"] for c in chunk_repo.created)
    assert document.status == "ready"

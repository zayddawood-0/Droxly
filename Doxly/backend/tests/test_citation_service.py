import uuid

from app.services.citation_service import CitationInput, CitationService
from app.services.retrieval_service import ContextItem


class _FakeCitationRepository:
    """skills/backend.md §3 — service unit-testable with a faked repository, independent of real FK-enforced persistence (already covered by tests/test_constraints.py's Citation constraint tests)."""

    def __init__(self) -> None:
        self.created: list[dict] = []

    async def create(self, **fields):
        self.created.append(fields)
        return fields


async def test_record_citations_persists_one_row_per_input():
    repo = _FakeCitationRepository()
    service = CitationService(repo)
    message_id = uuid.uuid4()
    citations = [
        CitationInput(
            document_chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            page_number=3,
            snippet="revenue grew 12% year over year",
            relevance_score=0.91,
        ),
        CitationInput(
            document_chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            page_number=None,
            snippet="operating costs decreased",
            relevance_score=0.83,
        ),
    ]

    result = await service.record_citations(message_id, citations)

    assert len(result) == 2
    assert repo.created[0]["message_id"] == message_id
    assert repo.created[0]["snippet"] == "revenue grew 12% year over year"
    assert repo.created[1]["page_number"] is None


async def test_record_citations_with_no_citations_persists_nothing():
    repo = _FakeCitationRepository()
    service = CitationService(repo)

    result = await service.record_citations(uuid.uuid4(), [])

    assert result == []
    assert repo.created == []


def test_citation_input_from_context_item_defaults_to_the_full_chunk_as_snippet():
    item = ContextItem(
        document_chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="report.pdf",
        page_number=2,
        content="quarterly revenue grew significantly",
        token_count=5,
        similarity=0.88,
    )

    citation_input = CitationService.citation_input_from_context_item(item)

    assert citation_input.snippet == item.content
    assert citation_input.document_chunk_id == item.document_chunk_id
    assert citation_input.page_number == 2
    assert citation_input.relevance_score == 0.88


def test_citation_input_from_context_item_accepts_an_explicit_snippet_override():
    item = ContextItem(
        document_chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="report.pdf",
        page_number=2,
        content="quarterly revenue grew significantly, alongside several other factors",
        token_count=9,
        similarity=0.88,
    )

    citation_input = CitationService.citation_input_from_context_item(
        item, snippet="quarterly revenue grew significantly"
    )

    assert citation_input.snippet == "quarterly revenue grew significantly"

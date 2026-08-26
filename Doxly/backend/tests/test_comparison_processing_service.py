"""
tasks/remediation-plan.md R6 — ComparisonProcessingService, the
worker-invoked half of comparison (mirrors test_extraction_processing_
service.py's shape: real Postgres via `db_session`, real chunk repository,
FakeEmbeddingProvider, and a scripted FakeLLMProvider — no RQ/queue
involved, this exercises the graph-running orchestration directly).
"""

import uuid

from sqlalchemy import select

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.graphs.comparison import ClassifiedDifferences
from app.ai.llm import FakeLLMProvider
from app.models import Document, DocumentChunk
from app.models.observability import AiRequest
from app.repositories.comparison_repository import ComparisonRepository
from app.repositories.document_repository import DocumentChunkRepository
from app.repositories.observability_repository import AiRequestRepository
from app.services.comparison_processing_service import ComparisonProcessingService
from tests.conftest import make_user


async def _make_ready_document(
    db_session,
    user_id,
    *,
    contents: list[str],
    page_numbers: list[int | None] | None = None,
) -> Document:
    document = Document(
        user_id=user_id,
        file_name="doc.pdf",
        storage_key=str(uuid.uuid4()),
        mime_type="application/pdf",
        size_bytes=100,
        checksum_sha256="a" * 64,
        status="ready",
    )
    db_session.add(document)
    await db_session.flush()
    provider = FakeEmbeddingProvider()
    pages = (
        page_numbers if page_numbers is not None else list(range(1, len(contents) + 1))
    )
    for i, (content, page_number) in enumerate(zip(contents, pages, strict=True)):
        [vector] = await provider.embed_batch([content])
        db_session.add(
            DocumentChunk(
                user_id=user_id,
                document_id=document.id,
                chunk_index=i,
                content=content,
                page_number=page_number,
                char_start=0,
                char_end=len(content),
                token_count=len(content.split()),
                embedding=vector,
                embedding_model=provider.model_name,
            )
        )
    await db_session.flush()
    return document


def _build_service(db_session, llm: FakeLLMProvider) -> ComparisonProcessingService:
    return ComparisonProcessingService(
        ComparisonRepository(db_session),
        DocumentChunkRepository(db_session),
        AiRequestRepository(db_session),
        llm,
        FakeEmbeddingProvider(),
    )


async def _ai_requests_for(db_session, user_id, operation=None) -> list[AiRequest]:
    stmt = select(AiRequest).where(AiRequest.user_id == user_id)
    if operation is not None:
        stmt = stmt.where(AiRequest.operation == operation)
    return list((await db_session.execute(stmt)).scalars().all())


async def test_successful_comparison_detects_a_modification_with_real_page_numbers(
    db_session,
):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(
        db_session, user.id, contents=["The invoice total is $100."]
    )
    doc_b = await _make_ready_document(
        db_session, user.id, contents=["The invoice total is $150."]
    )
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=["The total changed from $100 to $150."],
        structured_responses=[ClassifiedDifferences(categories=["numeric"])],
    )
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "completed"
    result = updated.result_json
    assert result["alignment_quality"] in ("high", "medium")
    assert result["message"] is None
    assert result["additions"] == []
    assert result["deletions"] == []
    assert len(result["modifications"]) == 1
    modification = result["modifications"][0]
    assert modification["change_type"] == "numeric"
    assert modification["a_page_number"] == 1
    assert modification["b_page_number"] == 1
    assert modification["a_excerpt"] == "The invoice total is $100."
    assert modification["b_excerpt"] == "The invoice total is $150."
    assert modification["explanation"] == "The total changed from $100 to $150."


async def test_b_only_segment_becomes_an_addition_with_correct_page_number(db_session):
    """A segment present only in document B (no counterpart in A — the two
    documents have unequal segment counts) must surface as a `deletions`-free
    `additions` entry with `document="b"` and B's real page number, never
    silently dropped or misattributed to A."""
    user = await make_user(db_session)
    shared = "Shared opening content about the project."
    new_section = "Brand new second section with fresh material."
    doc_a = await _make_ready_document(db_session, user.id, contents=[shared])
    doc_b = await _make_ready_document(
        db_session, user.id, contents=[shared, new_section]
    )
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider(
        structured_responses=[ClassifiedDifferences(categories=["wording"])]
    )
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "completed"
    result = updated.result_json
    assert result["deletions"] == []
    assert result["modifications"] == []
    assert len(result["additions"]) == 1
    addition = result["additions"][0]
    assert addition["document"] == "b"
    assert addition["page_number"] == 2
    assert addition["excerpt"] == new_section

    # The identical shared segment produces no difference at all (never an
    # LLM call); only change_classification_node's single batched call over
    # the one real difference (the addition) happens.
    assert len(llm.calls) == 1
    assert llm.calls[0]["structured"] is True


async def test_a_only_segment_becomes_a_deletion_with_correct_page_number(db_session):
    """A segment present only in document A (no counterpart in B) must
    surface as an `additions`-free `deletions` entry with `document="a"`
    and A's real page number."""
    user = await make_user(db_session)
    shared = "Shared opening content about the project."
    old_section = "Content that only existed in the old version."
    doc_a = await _make_ready_document(
        db_session, user.id, contents=[shared, old_section]
    )
    doc_b = await _make_ready_document(db_session, user.id, contents=[shared])
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider(
        structured_responses=[ClassifiedDifferences(categories=["wording"])]
    )
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "completed"
    result = updated.result_json
    assert result["additions"] == []
    assert result["modifications"] == []
    assert len(result["deletions"]) == 1
    deletion = result["deletions"][0]
    assert deletion["document"] == "a"
    assert deletion["page_number"] == 2
    assert deletion["excerpt"] == old_section


async def test_page_number_is_null_when_source_chunks_have_no_page_concept(db_session):
    """Not every mime type carries a page number (document-processing.md —
    e.g. text/plain has none); a modification sourced from such chunks must
    surface `a_page_number`/`b_page_number` as null, never a fabricated
    value and never silently dropped from the response shape."""
    user = await make_user(db_session)
    doc_a = await _make_ready_document(
        db_session,
        user.id,
        contents=["The invoice total is $100."],
        page_numbers=[None],
    )
    doc_b = await _make_ready_document(
        db_session,
        user.id,
        contents=["The invoice total is $150."],
        page_numbers=[None],
    )
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=["The total changed from $100 to $150."],
        structured_responses=[ClassifiedDifferences(categories=["numeric"])],
    )
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "completed"
    modification = updated.result_json["modifications"][0]
    assert modification["a_page_number"] is None
    assert modification["b_page_number"] is None


async def test_large_single_chunk_is_not_re_chunked_into_multiple_segments(db_session):
    """
    R6 compatibility fix regression guard: a single, already-processed
    DocumentChunk larger than `chunking.py`'s own ~800-token chunk-size
    target must still be treated as exactly one alignment segment.
    `semantic_alignment_node` used to re-chunk each document's *flattened*
    full text from scratch (`chunk_text()`), which would have split a chunk
    this large into multiple sub-segments, producing more than one
    modification/LLM call for what is genuinely a single source chunk.
    """
    user = await make_user(db_session)
    large_content_a = "This is a sentence about the quarterly report. " * 60
    large_content_b = "This is a sentence about the annual report. " * 60
    doc_a = await _make_ready_document(db_session, user.id, contents=[large_content_a])
    doc_b = await _make_ready_document(db_session, user.id, contents=[large_content_b])
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=["Changed 'quarterly' to 'annual' throughout."],
        structured_responses=[ClassifiedDifferences(categories=["wording"])],
    )
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "completed"
    # Exactly one segment per side means exactly one modification — if the
    # old re-chunking behavior were still active, this large blob would
    # have been split into multiple sub-chunks by chunk_text(), producing
    # more than one aligned pair/modification/LLM call.
    assert len(updated.result_json["modifications"]) == 1
    assert updated.result_json["modifications"][0]["a_page_number"] == 1
    assert updated.result_json["modifications"][0]["b_page_number"] == 1

    comparison_rows = await _ai_requests_for(db_session, user.id, "comparison")
    assert len(comparison_rows) == 2  # exactly 1 generate() + 1 generate_structured()


async def test_degraded_comparison_for_structurally_unrelated_documents(db_session):
    """FR-COMP-003 — a success path, not a failure."""
    user = await make_user(db_session)
    doc_a = await _make_ready_document(
        db_session,
        user.id,
        contents=["A resume describing five years of backend engineering."],
    )
    doc_b = await _make_ready_document(
        db_session, user.id, contents=["A recipe for chocolate chip cookies."]
    )
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider()  # never called on the degraded path
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "completed"
    result = updated.result_json
    assert result["alignment_quality"] == "low"
    assert result["message"] is not None
    assert result["additions"] == []
    assert result["deletions"] == []
    assert result["modifications"] == []

    # Degraded path makes no LLM call, but embedding calls still happened
    # (semantic alignment must run to determine confidence in the first
    # place) — both must still be logged (NFR-OBS-001).
    comparison_rows = await _ai_requests_for(db_session, user.id, "comparison")
    embedding_rows = await _ai_requests_for(db_session, user.id, "embedding")
    assert comparison_rows == []
    assert len(embedding_rows) == 2


async def test_failed_comparison_when_a_document_has_no_extractable_text(db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, user.id, contents=[])
    doc_b = await _make_ready_document(
        db_session, user.id, contents=["Some real content."]
    )
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider()
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "failed"
    assert updated.result_json["alignment_quality"] == "low"
    assert updated.result_json["additions"] == []


async def test_ai_requests_logs_one_row_per_real_provider_call(db_session):
    """
    R6's explicit observability decision (approved before implementation):
    unlike R4/R5's "one row per run," every real generate()/
    generate_structured()/embed_batch() call gets its own ai_requests row —
    two modified segments here must produce two "comparison"-operation rows
    for difference_detection_node's two generate() calls, plus one more for
    change_classification_node's single generate_structured() call, plus
    two "embedding"-operation rows (one embed_batch call per document).
    """
    user = await make_user(db_session)
    doc_a = await _make_ready_document(
        db_session,
        user.id,
        contents=["The invoice total is $100.", "Delivery date is March 1st."],
    )
    doc_b = await _make_ready_document(
        db_session,
        user.id,
        contents=["The invoice total is $150.", "Delivery date is March 5th."],
    )
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=[
            "The total changed from $100 to $150.",
            "The delivery date moved from March 1st to March 5th.",
        ],
        structured_responses=[ClassifiedDifferences(categories=["numeric", "factual"])],
    )
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    comparison_rows = await _ai_requests_for(db_session, user.id, "comparison")
    embedding_rows = await _ai_requests_for(db_session, user.id, "embedding")
    assert len(comparison_rows) == 3  # 2 generate() + 1 generate_structured()
    assert len(embedding_rows) == 2  # embed_batch(doc_a) + embed_batch(doc_b)
    assert all(row.status == "success" for row in comparison_rows)
    assert all(row.status == "success" for row in embedding_rows)
    assert all(row.provider == "fake" for row in comparison_rows + embedding_rows)
    # Real, non-fabricated token counts on every row.
    assert all(
        row.input_tokens is not None and row.input_tokens > 0 for row in comparison_rows
    )
    assert all(
        row.output_tokens is not None and row.output_tokens > 0
        for row in comparison_rows
    )
    assert all(
        row.input_tokens is not None and row.input_tokens > 0 for row in embedding_rows
    )
    assert all(row.output_tokens is None for row in embedding_rows)

    # Token usage is attached to the CORRECT call's own record, not
    # conflated/shared across calls: the two generate() calls' responses
    # have different real word counts (FakeLLMProvider's own token
    # accounting), and both must appear as distinct rows' output_tokens —
    # proof each row reflects its own call rather than a single collapsed
    # or duplicated value.
    first_response_text = "The total changed from $100 to $150."
    second_response_text = "The delivery date moved from March 1st to March 5th."
    expected_generate_output_tokens = {
        len(first_response_text.split()),
        len(second_response_text.split()),
    }
    actual_output_tokens = {row.output_tokens for row in comparison_rows}
    assert expected_generate_output_tokens <= actual_output_tokens
    assert len({row.output_tokens for row in comparison_rows}) == len(comparison_rows)


async def test_ai_requests_logs_error_row_on_structural_output_failure(db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(
        db_session, user.id, contents=["The invoice total is $100."]
    )
    doc_b = await _make_ready_document(
        db_session, user.id, contents=["The invoice total is $150."]
    )
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=["The total changed from $100 to $150."],
        structured_responses=[],  # generate_structured raises with nothing queued
    )
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)

    # change_classification_node catches StructuredOutputError itself and
    # degrades to a safe default category — the comparison still succeeds
    # overall (comparison.py's own documented degrade-not-crash behavior).
    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "completed"
    assert updated.result_json["modifications"][0]["change_type"] == "wording"

    comparison_rows = await _ai_requests_for(db_session, user.id, "comparison")
    assert len(comparison_rows) == 2  # 1 generate() + 1 failed generate_structured()
    failed_rows = [row for row in comparison_rows if row.status == "error"]
    assert len(failed_rows) == 1
    assert failed_rows[0].error_code == "structured_output_failed"


async def test_missing_comparison_is_silently_skipped(db_session):
    user = await make_user(db_session)
    llm = FakeLLMProvider()
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, uuid.uuid4())  # must not raise

    assert await _ai_requests_for(db_session, user.id) == []


async def test_already_terminal_comparison_is_a_no_op(db_session):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(db_session, user.id, contents=["a"])
    doc_b = await _make_ready_document(db_session, user.id, contents=["b"])
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={
            "alignment_quality": "high",
            "message": None,
            "additions": [],
            "deletions": [],
            "modifications": [],
        },
        status="completed",
    )
    llm = FakeLLMProvider()  # would raise if actually invoked
    service = _build_service(db_session, llm)

    await service.run_comparison(user.id, comparison.id)  # must not raise

    unchanged = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert unchanged.status == "completed"
    assert unchanged.result_json["alignment_quality"] == "high"


async def test_ai_request_logging_failure_does_not_affect_comparison_outcome(
    db_session,
):
    user = await make_user(db_session)
    doc_a = await _make_ready_document(
        db_session, user.id, contents=["The invoice total is $100."]
    )
    doc_b = await _make_ready_document(
        db_session, user.id, contents=["The invoice total is $150."]
    )
    comparison = await ComparisonRepository(db_session).create(
        user.id,
        document_a_id=doc_a.id,
        document_b_id=doc_b.id,
        result_json={},
        status="processing",
    )
    llm = FakeLLMProvider(
        responses=["The total changed from $100 to $150."],
        structured_responses=[ClassifiedDifferences(categories=["numeric"])],
    )

    class _FailingAiRequestRepository(AiRequestRepository):
        async def create(self, user_id, **fields):
            raise RuntimeError("observability store unavailable")

    service = ComparisonProcessingService(
        ComparisonRepository(db_session),
        DocumentChunkRepository(db_session),
        _FailingAiRequestRepository(db_session),
        llm,
        FakeEmbeddingProvider(),
    )

    await service.run_comparison(user.id, comparison.id)  # must not raise

    updated = await ComparisonRepository(db_session).get(user.id, comparison.id)
    assert updated.status == "completed"

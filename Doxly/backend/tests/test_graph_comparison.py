import uuid

from app.ai.embeddings import FakeEmbeddingProvider
from app.ai.graphs.comparison import (
    ALIGNMENT_CONFIDENCE_THRESHOLD,
    ClassifiedDifferences,
    build_comparison_graph,
    content_extraction_node,
)
from app.ai.llm import FakeLLMProvider


def _thread_config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def _base_state(**overrides):
    state = {
        "user_id": uuid.uuid4(),
        "document_a_id": uuid.uuid4(),
        "document_b_id": uuid.uuid4(),
        "text_a": "The invoice total is $100. Payment is due within 30 days of receipt.",
        "text_b": "The invoice total is $150. Payment is due within 30 days of receipt.",
    }
    state.update(overrides)
    return state


# --- Node-level unit tests ---


def test_content_extraction_fails_when_either_text_is_missing():
    result = content_extraction_node({"text_a": "", "text_b": "something"})
    assert result["status"] == "failed"
    assert "extractable text" in result["error"]


def test_content_extraction_passes_through_when_both_texts_present():
    result = content_extraction_node({"text_a": "a", "text_b": "b"})
    assert result == {}


# --- Full-graph routing tests ---


async def test_graph_detects_and_classifies_a_numeric_change():
    llm = FakeLLMProvider(
        responses=["The total amount changed from $100 to $150."],
        structured_responses=[ClassifiedDifferences(categories=["numeric"])],
    )
    graph = build_comparison_graph(llm, FakeEmbeddingProvider())

    result = await graph.ainvoke(_base_state(), config=_thread_config())

    assert result["status"] == "success"
    assert result["degraded"] is False
    assert result["alignment_confidence"] >= ALIGNMENT_CONFIDENCE_THRESHOLD
    assert len(result["classified_changes"]) == 1
    assert result["classified_changes"][0].category == "numeric"


async def test_graph_degrades_gracefully_for_structurally_unrelated_documents():
    """FR-COMP-003 — a success path, not a failure, when alignment isn't meaningful."""
    llm = FakeLLMProvider()
    graph = build_comparison_graph(llm, FakeEmbeddingProvider())

    result = await graph.ainvoke(
        _base_state(
            text_a="A resume describing five years of backend software engineering experience.",
            text_b="A recipe for baking chocolate chip cookies with butter and sugar.",
        ),
        config=_thread_config(),
    )

    assert result["status"] == "success"
    assert result["degraded"] is True
    assert result["alignment_confidence"] < ALIGNMENT_CONFIDENCE_THRESHOLD
    assert result["classified_changes"] == []
    # Degraded path never calls the LLM — no meaningful diff to describe.
    assert llm.calls == []


async def test_graph_fails_when_a_document_has_no_extractable_text():
    llm = FakeLLMProvider()
    graph = build_comparison_graph(llm, FakeEmbeddingProvider())

    result = await graph.ainvoke(_base_state(text_a="   "), config=_thread_config())

    assert result["status"] == "failed"
    assert "extractable text" in result["error"]


async def test_unmatched_segments_become_additions_without_an_llm_call():
    llm = FakeLLMProvider(
        structured_responses=[ClassifiedDifferences(categories=["structural"])]
    )
    graph = build_comparison_graph(llm, FakeEmbeddingProvider())

    # shared_paragraph alone is already near the chunker's ~800-token
    # ceiling, so appending new_section forces a clean split at the
    # paragraph boundary (no content mixing) — otherwise the chunker packs
    # both into one chunk, diluting the match and this test's premise along
    # with it (a real failure mode caught while first writing this test).
    shared_paragraph = (
        "A shared opening paragraph about the project scope and goals. " * 100
    )
    new_section = "This is an entirely new closing section with fresh content. " * 100
    result = await graph.ainvoke(
        _base_state(
            text_a=shared_paragraph,
            text_b=shared_paragraph + "\n\n" + new_section,
        ),
        config=_thread_config(),
    )

    assert result["status"] == "success"
    assert any(d.type == "addition" for d in result["classified_changes"])

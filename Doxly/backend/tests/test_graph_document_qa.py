import uuid

from app.ai.graphs.document_qa import (
    NO_ANSWER_RESPONSE,
    OUT_OF_SCOPE_RESPONSE,
    build_document_qa_graph,
    citation_validator_node,
    classifier_node,
)
from app.ai.llm import FakeLLMProvider
from app.services.retrieval_service import AssembledContext, ContextItem


class _FakeRetrieval:
    def __init__(self, context: AssembledContext) -> None:
        self._context = context

    async def retrieve(self, user_id, query, **kwargs):
        return self._context


def _thread_config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def _context_item(content: str) -> ContextItem:
    return ContextItem(
        document_chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="report.pdf",
        page_number=3,
        content=content,
        token_count=len(content.split()),
        similarity=0.9,
    )


# --- Node-level unit tests (testing.md §4.1: independently unit-testable, LLM mocked) ---


async def test_classifier_node_routes_factual_qa():
    llm = FakeLLMProvider(responses=["factual_qa"])
    result = await classifier_node({"query": "what is the revenue?"}, llm)
    assert result["intent"] == "factual_qa"


async def test_classifier_node_routes_out_of_scope():
    llm = FakeLLMProvider(responses=["out_of_scope"])
    result = await classifier_node({"query": "hello!"}, llm)
    assert result["intent"] == "out_of_scope"


def test_citation_validator_forces_fallback_when_ungrounded():
    context = AssembledContext(
        items=[_context_item("revenue grew significantly")], total_tokens=3
    )
    result = citation_validator_node(
        {
            "assembled_context": context,
            "draft_answer": "The sky is blue and grass is green.",
        }
    )
    assert result["draft_answer"] == NO_ANSWER_RESPONSE
    assert result["citations"] == []


def test_citation_validator_grounds_a_relevant_answer():
    context = AssembledContext(
        items=[_context_item("quarterly revenue grew twelve percent this year")],
        total_tokens=6,
    )
    result = citation_validator_node(
        {
            "assembled_context": context,
            "draft_answer": "Quarterly revenue grew twelve percent.",
        }
    )
    assert len(result["citations"]) == 1
    assert result["status"] == "success"


# --- Full-graph routing tests (every conditional edge, deterministically) ---


async def test_graph_routes_out_of_scope_query_without_retrieving():
    llm = FakeLLMProvider(responses=["out_of_scope"])
    retrieval = _FakeRetrieval(AssembledContext(items=[], total_tokens=0))
    graph = build_document_qa_graph(llm, retrieval)

    result = await graph.ainvoke(
        {"user_id": uuid.uuid4(), "query": "hi there"}, config=_thread_config()
    )

    assert result["draft_answer"] == OUT_OF_SCOPE_RESPONSE
    # No LLM call beyond the classifier — the answer generator was never reached.
    assert len(llm.calls) == 1


async def test_graph_routes_empty_context_to_no_answer_without_generating():
    llm = FakeLLMProvider(responses=["factual_qa"])
    retrieval = _FakeRetrieval(AssembledContext(items=[], total_tokens=0))
    graph = build_document_qa_graph(llm, retrieval)

    result = await graph.ainvoke(
        {"user_id": uuid.uuid4(), "query": "what is the revenue?"},
        config=_thread_config(),
    )

    assert result["draft_answer"] == NO_ANSWER_RESPONSE
    assert result["citations"] == []
    assert (
        len(llm.calls) == 1
    )  # classifier only — answer generator never called (FR-RAG-003)


async def test_graph_produces_a_grounded_answer_with_citations():
    item = _context_item("revenue grew twelve percent year over year")
    llm = FakeLLMProvider(
        responses=["factual_qa", "Revenue grew twelve percent year over year."]
    )
    retrieval = _FakeRetrieval(AssembledContext(items=[item], total_tokens=6))
    graph = build_document_qa_graph(llm, retrieval)

    result = await graph.ainvoke(
        {"user_id": uuid.uuid4(), "query": "how much did revenue grow?"},
        config=_thread_config(),
    )

    assert result["status"] == "success"
    assert result["draft_answer"] == "Revenue grew twelve percent year over year."
    assert len(result["citations"]) == 1
    assert result["citations"][0].document_chunk_id == item.document_chunk_id


async def test_graph_forces_fallback_when_generation_drifts_from_context():
    item = _context_item("revenue grew twelve percent year over year")
    llm = FakeLLMProvider(
        responses=["factual_qa", "I like pizza and long walks on the beach."]
    )
    retrieval = _FakeRetrieval(AssembledContext(items=[item], total_tokens=6))
    graph = build_document_qa_graph(llm, retrieval)

    result = await graph.ainvoke(
        {"user_id": uuid.uuid4(), "query": "how much did revenue grow?"},
        config=_thread_config(),
    )

    assert result["draft_answer"] == NO_ANSWER_RESPONSE
    assert result["citations"] == []

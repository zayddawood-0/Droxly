import uuid

from app.ai.graphs.extraction import (
    PRESET_TEMPLATES,
    ExtractedField,
    _build_result_model,
    build_extraction_graph,
    schema_generator_node,
)
from app.ai.llm import FakeLLMProvider, StructuredOutputError
from app.services.retrieval_service import AssembledContext, ContextItem


class _FakeRetrieval:
    def __init__(self, context: AssembledContext | None = None) -> None:
        self._context = context or AssembledContext(
            items=[
                ContextItem(
                    document_chunk_id=uuid.uuid4(),
                    document_id=uuid.uuid4(),
                    document_title="invoice.pdf",
                    page_number=1,
                    content="Invoice #123 dated 2026-01-01 from Acme Corp, total $500",
                    token_count=10,
                    similarity=0.9,
                )
            ],
            total_tokens=10,
        )

    async def retrieve(self, user_id, query, **kwargs):
        return self._context


def _thread_config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def _base_state(**overrides):
    state = {
        "user_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "retry_count": 0,
    }
    state.update(overrides)
    return state


# --- Node-level unit tests ---


def test_schema_generator_prefers_requested_schema():
    custom = {"custom_field": "string"}
    result = schema_generator_node(
        {"requested_schema": custom, "document_type": "invoice"}
    )
    assert result["resolved_schema_json"] == custom


def test_schema_generator_falls_back_to_template_key():
    result = schema_generator_node(
        {"template_key": "resume", "document_type": "invoice"}
    )
    assert result["resolved_schema_json"] == PRESET_TEMPLATES["resume"]


def test_schema_generator_falls_back_to_classified_document_type():
    result = schema_generator_node({"document_type": "contract"})
    assert result["resolved_schema_json"] == PRESET_TEMPLATES["contract"]


def test_schema_generator_falls_back_to_generic_when_nothing_matches():
    result = schema_generator_node({"document_type": "other"})
    assert result["resolved_schema_json"] == PRESET_TEMPLATES["generic"]


def test_extracted_field_never_requires_a_fabricated_value():
    """FR-EXT-003 — found=False with a reason is a fully valid instance, not a workaround."""
    field = ExtractedField(
        value=None, found=False, reason="not mentioned in the document"
    )
    assert field.value is None
    assert field.found is False


# --- Full-graph routing tests ---


async def test_graph_classifies_resolves_schema_and_extracts():
    result_model = _build_result_model(PRESET_TEMPLATES["invoice"])
    fake_result = result_model(
        invoice_number=ExtractedField(value="123", confidence=0.9, source_page=1),
        invoice_date=ExtractedField(value="2026-01-01", confidence=0.9, source_page=1),
        vendor_name=ExtractedField(value="Acme Corp", confidence=0.9, source_page=1),
        total_amount=ExtractedField(value="500", confidence=0.9, source_page=1),
        due_date=ExtractedField(
            value=None, found=False, reason="not mentioned in the document"
        ),
    )
    llm = FakeLLMProvider(responses=["invoice"], structured_responses=[fake_result])
    graph = build_extraction_graph(llm, _FakeRetrieval())

    result = await graph.ainvoke(_base_state(), config=_thread_config())

    assert result["status"] == "success"
    assert result["document_type"] == "invoice"
    assert set(result["resolved_schema_json"].keys()) == set(
        PRESET_TEMPLATES["invoice"].keys()
    )
    assert result["validated_result"]["due_date"]["found"] is False
    assert result["validated_result"]["due_date"]["value"] is None
    assert result["validated_result"]["vendor_name"]["value"] == "Acme Corp"


async def test_graph_falls_through_to_generic_schema_on_unclassifiable_document():
    result_model = _build_result_model(PRESET_TEMPLATES["generic"])
    fake_result = result_model(
        summary=ExtractedField(value="A short document.", confidence=0.5),
        key_facts=ExtractedField(
            value=None, found=False, reason="no clear facts present"
        ),
    )
    llm = FakeLLMProvider(responses=["other"], structured_responses=[fake_result])
    graph = build_extraction_graph(llm, _FakeRetrieval())

    result = await graph.ainvoke(_base_state(), config=_thread_config())

    assert result["status"] == "success"
    assert result["document_type"] == "other"
    assert set(result["resolved_schema_json"].keys()) == set(
        PRESET_TEMPLATES["generic"].keys()
    )


async def test_graph_retries_once_on_structural_failure_then_succeeds():
    result_model = _build_result_model(PRESET_TEMPLATES["generic"])
    fake_result = result_model(
        summary=ExtractedField(value="Recovered on retry."),
        key_facts=ExtractedField(value=None, found=False, reason="n/a"),
    )
    llm = FakeLLMProvider(
        responses=["other"],
        structured_responses=[StructuredOutputError("malformed JSON"), fake_result],
    )
    graph = build_extraction_graph(llm, _FakeRetrieval())

    result = await graph.ainvoke(_base_state(), config=_thread_config())

    assert result["status"] == "success"
    assert result["retry_count"] == 1


async def test_graph_fails_terminally_after_two_structural_failures():
    llm = FakeLLMProvider(
        responses=["other"],
        structured_responses=[
            StructuredOutputError("malformed JSON"),
            StructuredOutputError("still malformed"),
        ],
    )
    graph = build_extraction_graph(llm, _FakeRetrieval())

    result = await graph.ainvoke(_base_state(), config=_thread_config())

    assert result["status"] == "failed"
    assert "still malformed" in result["error"]

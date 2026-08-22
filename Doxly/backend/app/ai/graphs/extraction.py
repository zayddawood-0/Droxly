import uuid
from typing import Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, create_model

from app.ai.llm import LLMProvider, Message, StructuredOutputError
from app.services.retrieval_service import RetrievalService

DocumentType = Literal["invoice", "contract", "resume", "research_paper", "other"]

# FR-EXT-002's Template Gallery — preset field schemas per document type; a
# generic key-fact schema is the last-resort default so extraction always
# has something to do (langgraph.md §4 node 2).
PRESET_TEMPLATES: dict[str, dict[str, str]] = {
    "invoice": {
        "invoice_number": "string",
        "invoice_date": "string",
        "vendor_name": "string",
        "total_amount": "string",
        "due_date": "string",
    },
    "contract": {
        "parties": "string",
        "effective_date": "string",
        "term_length": "string",
        "governing_law": "string",
        "termination_clause": "string",
    },
    "resume": {
        "candidate_name": "string",
        "email": "string",
        "years_experience": "string",
        "most_recent_title": "string",
        "education": "string",
    },
    "research_paper": {
        "title": "string",
        "authors": "string",
        "abstract": "string",
        "publication_year": "string",
        "key_findings": "string",
    },
    "generic": {"summary": "string", "key_facts": "string"},
}

# langgraph.md §4 — "one retry of Extraction Agent... a second structural
# failure routes to terminal failure."
MAX_STRUCTURAL_RETRIES = 1


class ExtractedField(BaseModel):
    """
    A single extraction result field — always this shape, never a bare
    scalar, so the model has a place to say "not found" instead of
    inventing a value (FR-EXT-003, ai.md §5 step 4).
    """

    value: str | None = None
    found: bool = True
    reason: str | None = None
    confidence: float | None = None
    source_page: int | None = None
    source_snippet: str | None = None


class ExtractionState(TypedDict, total=False):
    """langgraph.md §4's Extraction state."""

    user_id: uuid.UUID
    document_id: uuid.UUID
    template_key: str | None
    requested_schema: dict[str, str] | None
    document_type: DocumentType
    resolved_schema_json: dict[str, str]
    raw_extraction: BaseModel | None
    validated_result: dict | None
    retry_count: int
    status: Literal["success", "failed"]
    error: str | None


async def document_classifier_node(
    state: ExtractionState, llm: LLMProvider, retrieval: RetrievalService
) -> dict:
    """langgraph.md §4 node 1 — FAST tier, grounded in retrieved excerpts (rag.md) rather than a raw document dump."""
    context = await retrieval.retrieve(
        state["user_id"],
        "document type and purpose",
        document_id=state["document_id"],
        token_budget=800,
    )
    excerpt = (
        "\n\n".join(item.content for item in context.items)
        or "(no extractable content)"
    )
    completion = await llm.generate(
        [Message("user", excerpt)],
        system_prompt=(
            "Classify this document as exactly one of: invoice, contract, resume, "
            "research_paper, other. Reply with only that single word."
        ),
        model_tier="fast",
        max_tokens=10,
    )
    guess = completion.text.strip().lower()
    document_type: DocumentType = guess if guess in PRESET_TEMPLATES or guess == "other" else "other"  # type: ignore[assignment]
    return {"document_type": document_type}


def schema_generator_node(state: ExtractionState) -> dict:
    """
    langgraph.md §4 node 2 — no LLM call. Precedence: user-supplied schema
    > user-picked template > auto-classified type > generic default
    (roadmap.md's "classification failure just falls through to the
    generic schema, not a graph failure").
    """
    if state.get("requested_schema"):
        return {"resolved_schema_json": state["requested_schema"]}
    key = state.get("template_key") or state.get("document_type") or "other"
    schema = PRESET_TEMPLATES.get(key, PRESET_TEMPLATES["generic"])
    return {"resolved_schema_json": schema}


def _build_result_model(schema: dict[str, str]) -> type[BaseModel]:
    fields = {name: (ExtractedField, ...) for name in schema}
    return create_model("ExtractionResult", **fields)  # type: ignore[call-overload]


async def extraction_agent_node(
    state: ExtractionState, llm: LLMProvider, retrieval: RetrievalService
) -> dict:
    """
    langgraph.md §4 node 3 — STANDARD tier, structured-output call
    constrained to resolved_schema_json. Grounds on retrieved chunks
    relevant to the requested fields (rag.md), never the whole document
    stuffed into one call.
    """
    schema = state["resolved_schema_json"]
    context = await retrieval.retrieve(
        state["user_id"],
        "Key facts: " + ", ".join(schema.keys()),
        document_id=state["document_id"],
    )
    context_block = "\n\n".join(
        f"[page {item.page_number}] {item.content}" for item in context.items
    )
    field_descriptions = "\n".join(
        f"- {name} ({type_})" for name, type_ in schema.items()
    )
    result_model = _build_result_model(schema)

    try:
        result = await llm.generate_structured(
            [
                Message(
                    "user",
                    f"<document_context>\n{context_block}\n</document_context>\n\n"
                    f"Extract these fields:\n{field_descriptions}",
                )
            ],
            system_prompt=(
                "Extract the requested fields strictly from the provided document "
                "context. For each field, if it cannot be located, set found=false "
                "and explain why in reason — never invent a value (FR-EXT-003)."
            ),
            output_schema=result_model,
            model_tier="standard",
        )
        return {
            "raw_extraction": result,
            "validated_result": result.model_dump(),
            "error": None,
        }
    except StructuredOutputError as exc:
        return {"error": str(exc), "retry_count": state.get("retry_count", 0) + 1}


def validation_node(state: ExtractionState) -> dict:
    """
    langgraph.md §4 node 4 — the Pydantic gate itself already ran inside
    Extraction Agent's `generate_structured` call (ai.md §5's "two gates,
    not one"); this node owns the remaining, distinct responsibility: the
    structural-failure retry-vs-fail routing decision.
    """
    return {}


def _validation_router(state: ExtractionState) -> str:
    if state.get("validated_result") is not None:
        return "valid"
    if state.get("retry_count", 0) <= MAX_STRUCTURAL_RETRIES:
        return "retry"
    return "fail"


def success_node(state: ExtractionState) -> dict:
    return {"status": "success", "error": None}


def failure_node(state: ExtractionState) -> dict:
    return {"status": "failed", "error": state.get("error") or "Extraction failed."}


def build_extraction_graph(
    llm: LLMProvider, retrieval: RetrievalService
) -> CompiledStateGraph:
    """langgraph.md §1.7 — background-worker graph, checkpointed."""

    async def _document_classifier(state: ExtractionState) -> dict:
        return await document_classifier_node(state, llm, retrieval)

    async def _extraction_agent(state: ExtractionState) -> dict:
        return await extraction_agent_node(state, llm, retrieval)

    graph = StateGraph(ExtractionState)
    graph.add_node("document_classifier", _document_classifier)
    graph.add_node("schema_generator", schema_generator_node)
    graph.add_node("extraction_agent", _extraction_agent)
    graph.add_node("validation", validation_node)
    graph.add_node("success", success_node)
    graph.add_node("failure", failure_node)

    graph.set_entry_point("document_classifier")
    graph.add_edge("document_classifier", "schema_generator")
    graph.add_edge("schema_generator", "extraction_agent")
    graph.add_edge("extraction_agent", "validation")
    graph.add_conditional_edges(
        "validation",
        _validation_router,
        {"valid": "success", "retry": "extraction_agent", "fail": "failure"},
    )
    graph.add_edge("success", END)
    graph.add_edge("failure", END)

    return graph.compile(checkpointer=MemorySaver())

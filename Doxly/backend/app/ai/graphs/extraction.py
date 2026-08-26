import uuid
from typing import Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, create_model

from app.ai.llm import LLMProvider, Message, StructuredOutputError
from app.services.retrieval_service import RetrievalService

DocumentType = Literal["invoice", "contract", "resume", "research_paper", "other"]

# FR-EXT-002's Template Gallery — the single source of truth for every
# preset's field schema, reused by both `GET /extractions/templates`
# (api.md §6, needs the full name/description/required metadata) and this
# graph's own Schema Generator node (needs only name/type per field to
# build the dynamic result model) — one registry, not two independently
# maintained field lists that could silently drift from each other.
# Each field is a plain dict (not a dataclass) because this is exactly the
# shape a user-supplied custom `schema` arrives in from the API request
# (api.md: `schema?: [{ name, type, description?, required }]`) and the
# shape persisted verbatim into `extractions.schema_json` (database.md
# §3.11) — one shape end-to-end, no adapter needed between "preset" and
# "custom" schemas once resolved.
PRESET_TEMPLATES: dict[str, dict] = {
    "invoice": {
        "name": "Invoice",
        "description": "Standard invoice fields: number, dates, vendor, and amount.",
        "fields": [
            {
                "name": "invoice_number",
                "type": "string",
                "description": "The invoice's own identifying number.",
                "required": True,
            },
            {
                "name": "invoice_date",
                "type": "string",
                "description": "The date the invoice was issued.",
                "required": True,
            },
            {
                "name": "vendor_name",
                "type": "string",
                "description": "The vendor/seller's name.",
                "required": True,
            },
            {
                "name": "total_amount",
                "type": "string",
                "description": "The total amount due.",
                "required": True,
            },
            {
                "name": "due_date",
                "type": "string",
                "description": "The payment due date.",
                "required": False,
            },
        ],
    },
    "contract": {
        "name": "Contract",
        "description": "Key contractual terms: parties, dates, governing law, and termination.",
        "fields": [
            {
                "name": "parties",
                "type": "string",
                "description": "The contracting parties.",
                "required": True,
            },
            {
                "name": "effective_date",
                "type": "string",
                "description": "The date the contract takes effect.",
                "required": True,
            },
            {
                "name": "term_length",
                "type": "string",
                "description": "The duration of the contract.",
                "required": False,
            },
            {
                "name": "governing_law",
                "type": "string",
                "description": "The jurisdiction whose law governs the contract.",
                "required": False,
            },
            {
                "name": "termination_clause",
                "type": "string",
                "description": "The conditions under which the contract may be terminated.",
                "required": False,
            },
        ],
    },
    "resume": {
        "name": "Resume",
        "description": "Candidate identity, experience, and education.",
        "fields": [
            {
                "name": "candidate_name",
                "type": "string",
                "description": "The candidate's full name.",
                "required": True,
            },
            {
                "name": "email",
                "type": "string",
                "description": "The candidate's contact email.",
                "required": False,
            },
            {
                "name": "years_experience",
                "type": "string",
                "description": "Total years of professional experience.",
                "required": False,
            },
            {
                "name": "most_recent_title",
                "type": "string",
                "description": "The candidate's most recent job title.",
                "required": False,
            },
            {
                "name": "education",
                "type": "string",
                "description": "The candidate's education history.",
                "required": False,
            },
        ],
    },
    "research_paper": {
        "name": "Research Paper",
        "description": "Title, authorship, and key findings of an academic paper.",
        "fields": [
            {
                "name": "title",
                "type": "string",
                "description": "The paper's title.",
                "required": True,
            },
            {
                "name": "authors",
                "type": "string",
                "description": "The paper's authors.",
                "required": True,
            },
            {
                "name": "abstract",
                "type": "string",
                "description": "The paper's abstract.",
                "required": False,
            },
            {
                "name": "publication_year",
                "type": "string",
                "description": "The year the paper was published.",
                "required": False,
            },
            {
                "name": "key_findings",
                "type": "string",
                "description": "The paper's key findings.",
                "required": False,
            },
        ],
    },
}

# langgraph.md §4 node 2 — "a generic key-fact schema is the last-resort
# default so extraction never has nothing to do." Deliberately NOT part of
# `PRESET_TEMPLATES`: it is never a valid `template_key` a user can request
# (api.md's create-extraction 422 validates `template_key` against the
# *named* presets only) and is never listed by `GET /extractions/templates`
# — it exists solely as the Schema Generator's own internal fallback for an
# unclassifiable ("other") document.
GENERIC_TEMPLATE_FIELDS: list[dict] = [
    {
        "name": "summary",
        "type": "string",
        "description": "A short summary of the document.",
        "required": True,
    },
    {
        "name": "key_facts",
        "type": "string",
        "description": "Key facts extracted from the document.",
        "required": False,
    },
]

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
    requested_schema: list[dict] | None
    document_type: DocumentType
    resolved_schema_json: list[dict]
    raw_extraction: BaseModel | None
    validated_result: dict | None
    retry_count: int
    status: Literal["success", "failed"]
    error: str | None
    # R5 (NFR-OBS-001) — real usage from the Extraction Agent's structured
    # call (the classifier's own FAST-tier `generate()` call already
    # returns a `Completion`; these three mirror it for the STANDARD-tier
    # call, which is what ExtractionService logs as the run's `ai_requests`
    # row, per this same run being one observability unit like chat's turn).
    extraction_input_tokens: int | None
    extraction_output_tokens: int | None
    extraction_model: str | None


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
    key = state.get("template_key") or state.get("document_type")
    template = PRESET_TEMPLATES.get(key) if key else None
    fields = template["fields"] if template else GENERIC_TEMPLATE_FIELDS
    return {"resolved_schema_json": fields}


def _build_result_model(schema: list[dict]) -> type[BaseModel]:
    fields = {field["name"]: (ExtractedField, ...) for field in schema}
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
        "Key facts: " + ", ".join(field["name"] for field in schema),
        document_id=state["document_id"],
    )
    context_block = "\n\n".join(
        f"[page {item.page_number}] {item.content}" for item in context.items
    )
    field_descriptions = "\n".join(
        f"- {field['name']} ({field['type']}){' [required]' if field.get('required') else ''}"
        f"{': ' + field['description'] if field.get('description') else ''}"
        for field in schema
    )
    result_model = _build_result_model(schema)

    try:
        completion = await llm.generate_structured(
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
            "raw_extraction": completion.result,
            "validated_result": completion.result.model_dump(),
            "extraction_input_tokens": completion.input_tokens,
            "extraction_output_tokens": completion.output_tokens,
            "extraction_model": completion.model,
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

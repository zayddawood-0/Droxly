import uuid
from typing import Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from app.ai.embeddings import EmbeddingProvider
from app.ai.llm import LLMProvider, Message, StructuredOutputError
from app.document_processing.chunking import chunk_text

ChangeCategory = Literal["factual", "numeric", "wording", "structural"]
DifferenceType = Literal["addition", "deletion", "modification"]

# langgraph.md §5: "if alignment_confidence falls below a defined
# threshold ... routes to a degraded-report terminal state." No specific
# numeric floor is given in the spec — 0.5 is this implementation's chosen
# parameter (documents scoring below "more alike than not" on average
# best-match cosine similarity are treated as too structurally different
# to diff meaningfully), revisitable like any other tuned threshold.
ALIGNMENT_CONFIDENCE_THRESHOLD = 0.5


class AlignedPair(BaseModel):
    segment_a: str | None
    segment_b: str | None
    similarity: float


class Difference(BaseModel):
    type: DifferenceType
    segment_a: str | None
    segment_b: str | None
    description: str
    category: ChangeCategory | None = None


class ClassifiedDifferences(BaseModel):
    categories: list[ChangeCategory]


class ComparisonState(TypedDict, total=False):
    """langgraph.md §5's Comparison state."""

    user_id: uuid.UUID
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    text_a: str
    text_b: str
    alignment_map: list[AlignedPair]
    alignment_confidence: float
    raw_differences: list[Difference]
    classified_changes: list[Difference]
    degraded: bool
    status: Literal["success", "failed"]
    error: str | None


def content_extraction_node(state: ComparisonState) -> dict:
    """
    langgraph.md §5 node 1 — "reuses the same extraction output already
    produced ... no re-parsing of the source file." `text_a`/`text_b`
    arrive as already-extracted input (no document-processing pipeline
    exists yet to fetch them from — the same "take the missing upstream
    stage as a parameter" pattern used throughout this backend track); this
    node's remaining job is presence validation.
    """
    if not state.get("text_a", "").strip() or not state.get("text_b", "").strip():
        return {
            "status": "failed",
            "error": "One or both documents have no extractable text to compare.",
        }
    return {}


async def semantic_alignment_node(
    state: ComparisonState, embeddings: EmbeddingProvider
) -> dict:
    """
    langgraph.md §5 node 2 — matches corresponding segments by meaning
    (embedding similarity), not raw position. A greedy best-match search
    over chunk embeddings — not globally optimal, but simple, deterministic,
    and adequate at the segment counts a single document comparison
    involves; reuses Phase 6's chunker rather than re-splitting text ad hoc.
    """
    chunks_a = chunk_text(state["text_a"])
    chunks_b = chunk_text(state["text_b"])
    if not chunks_a or not chunks_b:
        return {"alignment_map": [], "alignment_confidence": 0.0}

    vectors_a = await embeddings.embed_batch([c.content for c in chunks_a])
    vectors_b = await embeddings.embed_batch([c.content for c in chunks_b])

    used_b: set[int] = set()
    similarities: list[float] = []
    pairs: list[AlignedPair] = []

    for i, vector_a in enumerate(vectors_a):
        best_j, best_similarity = None, -1.0
        for j, vector_b in enumerate(vectors_b):
            if j in used_b:
                continue
            similarity = _cosine_similarity(vector_a, vector_b)
            if similarity > best_similarity:
                best_j, best_similarity = j, similarity
        if best_j is not None:
            used_b.add(best_j)
            similarities.append(best_similarity)
            pairs.append(
                AlignedPair(
                    segment_a=chunks_a[i].content,
                    segment_b=chunks_b[best_j].content,
                    similarity=best_similarity,
                )
            )
        else:
            pairs.append(
                AlignedPair(
                    segment_a=chunks_a[i].content, segment_b=None, similarity=0.0
                )
            )

    for j, chunk_b in enumerate(chunks_b):
        if j not in used_b:
            pairs.append(
                AlignedPair(segment_a=None, segment_b=chunk_b.content, similarity=0.0)
            )

    confidence = sum(similarities) / len(similarities) if similarities else 0.0
    return {"alignment_map": pairs, "alignment_confidence": confidence}


async def difference_detection_node(state: ComparisonState, llm: LLMProvider) -> dict:
    """langgraph.md §5 node 3 — unmatched segments are pure additions/deletions (no LLM call needed); aligned-but-differing pairs get a one-sentence description from the model."""
    differences: list[Difference] = []
    for pair in state["alignment_map"]:
        if pair.segment_a is None:
            differences.append(
                Difference(
                    type="addition",
                    segment_a=None,
                    segment_b=pair.segment_b,
                    description="New content added.",
                )
            )
            continue
        if pair.segment_b is None:
            differences.append(
                Difference(
                    type="deletion",
                    segment_a=pair.segment_a,
                    segment_b=None,
                    description="Content removed.",
                )
            )
            continue
        if pair.segment_a.strip() == pair.segment_b.strip():
            continue

        completion = await llm.generate(
            [
                Message(
                    "user",
                    f"Version A:\n{pair.segment_a}\n\nVersion B:\n{pair.segment_b}",
                )
            ],
            system_prompt="Describe in one concise sentence what changed between version A and version B.",
            model_tier="standard",
            max_tokens=100,
        )
        differences.append(
            Difference(
                type="modification",
                segment_a=pair.segment_a,
                segment_b=pair.segment_b,
                description=completion.text,
            )
        )
    return {"raw_differences": differences}


async def change_classification_node(state: ComparisonState, llm: LLMProvider) -> dict:
    """langgraph.md §5 node 4 — STANDARD tier (ai.md §3's "Comparison change-classification nodes"), one batched call classifying every detected difference rather than one call each."""
    differences = state["raw_differences"]
    if not differences:
        return {"classified_changes": []}

    numbered = "\n".join(f"{i}. {d.description}" for i, d in enumerate(differences))
    try:
        completion = await llm.generate_structured(
            [Message("user", numbered)],
            system_prompt=(
                "Classify each numbered change as exactly one of: factual, numeric, "
                "wording, structural. Return one category per change, in order."
            ),
            output_schema=ClassifiedDifferences,
            model_tier="standard",
        )
        categories = completion.result.categories
    except StructuredOutputError:
        categories = []

    # A classification miss degrades to a safe default rather than crashing
    # the whole comparison — the diff itself is still correct and useful
    # even if a category label is approximate.
    categories = (categories + ["wording"] * len(differences))[: len(differences)]
    classified = [
        difference.model_copy(update={"category": category})
        for difference, category in zip(differences, categories, strict=True)
    ]
    return {"classified_changes": classified}


def comparison_report_node(state: ComparisonState) -> dict:
    return {"status": "success", "error": None, "degraded": False}


def degraded_report_node(state: ComparisonState) -> dict:
    """langgraph.md §5 — a success path (FR-COMP-003's graceful degradation), not a failure: the documents were too structurally different to align, and the report says so rather than forcing a misleading diff."""
    return {
        "raw_differences": [],
        "classified_changes": [],
        "status": "success",
        "error": None,
        "degraded": True,
    }


def failure_node(state: ComparisonState) -> dict:
    return {"status": "failed", "error": state.get("error") or "Comparison failed."}


def _extraction_router(state: ComparisonState) -> str:
    return "failed" if state.get("status") == "failed" else "ok"


def _alignment_router(state: ComparisonState) -> str:
    return (
        "degraded"
        if state["alignment_confidence"] < ALIGNMENT_CONFIDENCE_THRESHOLD
        else "aligned"
    )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_comparison_graph(
    llm: LLMProvider, embeddings: EmbeddingProvider
) -> CompiledStateGraph:
    """langgraph.md §1.7 — background-worker graph, checkpointed."""

    async def _semantic_alignment(state: ComparisonState) -> dict:
        return await semantic_alignment_node(state, embeddings)

    async def _difference_detection(state: ComparisonState) -> dict:
        return await difference_detection_node(state, llm)

    async def _change_classification(state: ComparisonState) -> dict:
        return await change_classification_node(state, llm)

    graph = StateGraph(ComparisonState)
    graph.add_node("content_extraction", content_extraction_node)
    graph.add_node("semantic_alignment", _semantic_alignment)
    graph.add_node("difference_detection", _difference_detection)
    graph.add_node("change_classification", _change_classification)
    graph.add_node("comparison_report", comparison_report_node)
    graph.add_node("degraded_report", degraded_report_node)
    graph.add_node("failure", failure_node)

    graph.set_entry_point("content_extraction")
    graph.add_conditional_edges(
        "content_extraction",
        _extraction_router,
        {"ok": "semantic_alignment", "failed": "failure"},
    )
    graph.add_conditional_edges(
        "semantic_alignment",
        _alignment_router,
        {"aligned": "difference_detection", "degraded": "degraded_report"},
    )
    graph.add_edge("difference_detection", "change_classification")
    graph.add_edge("change_classification", "comparison_report")
    graph.add_edge("comparison_report", END)
    graph.add_edge("degraded_report", END)
    graph.add_edge("failure", END)

    return graph.compile(checkpointer=MemorySaver())

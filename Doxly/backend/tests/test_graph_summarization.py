import uuid

from app.ai.graphs.summarization import (
    MAP_REDUCE_TOKEN_THRESHOLD,
    QualityCheckResult,
    build_summarization_graph,
    content_analyzer_node,
)
from app.ai.llm import FakeLLMProvider


def _thread_config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def _base_state(**overrides):
    state = {
        "user_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "summary_type": "brief",
        "document_text": "A modest document about quarterly performance.",
        "retry_count": 0,
    }
    state.update(overrides)
    return state


# --- Node-level unit tests ---


def test_content_analyzer_picks_single_pass_for_short_text():
    result = content_analyzer_node({"document_text": "A short document."})
    assert result["structure_profile"]["strategy"] == "single_pass"


def test_content_analyzer_picks_map_reduce_for_long_text():
    long_text = (
        "This is a sentence with real words. " * 2000
    )  # well over the token threshold
    result = content_analyzer_node({"document_text": long_text})
    assert result["structure_profile"]["token_count"] > MAP_REDUCE_TOKEN_THRESHOLD
    assert result["structure_profile"]["strategy"] == "map_reduce"


# --- Full-graph routing tests ---


async def test_graph_passes_on_the_first_attempt():
    llm = FakeLLMProvider(
        responses=["A concise summary."],
        structured_responses=[QualityCheckResult(passed=True)],
    )
    graph = build_summarization_graph(llm)

    result = await graph.ainvoke(_base_state(), config=_thread_config())

    assert result["status"] == "success"
    assert result["draft_summary"] == "A concise summary."
    assert result["retry_count"] == 0


async def test_graph_retries_up_to_twice_then_succeeds():
    llm = FakeLLMProvider(
        responses=["attempt 1", "attempt 2", "attempt 3"],
        structured_responses=[
            QualityCheckResult(passed=False, feedback="too vague"),
            QualityCheckResult(passed=False, feedback="still too vague"),
            QualityCheckResult(passed=True),
        ],
    )
    graph = build_summarization_graph(llm)

    result = await graph.ainvoke(_base_state(), config=_thread_config())

    assert result["status"] == "success"
    assert result["draft_summary"] == "attempt 3"
    assert result["retry_count"] == 2


async def test_graph_fails_after_exhausting_the_retry_budget():
    """langgraph.md §3 — 'up to 2 retries (3 total attempts)', then terminal failure."""
    llm = FakeLLMProvider(
        responses=["a1", "a2", "a3"],
        structured_responses=[
            QualityCheckResult(passed=False, feedback="bad"),
            QualityCheckResult(passed=False, feedback="bad"),
            QualityCheckResult(passed=False, feedback="still bad"),
        ],
    )
    graph = build_summarization_graph(llm)

    result = await graph.ainvoke(_base_state(), config=_thread_config())

    assert result["status"] == "failed"
    assert "still bad" in result["error"]
    assert len(llm.calls) == 6  # 3 generate + 3 structured quality-check calls


async def test_map_reduce_strategy_summarizes_each_chunk_then_combines():
    long_text = (
        "This document discusses quarterly revenue growth in great detail. " * 400
    )
    llm = FakeLLMProvider(
        responses=["combined summary"],
        structured_responses=[QualityCheckResult(passed=True)],
    )
    # Any number of per-chunk summaries plus the final combine call all pull
    # from the same responses queue; supply enough for every chunk + 1 final.
    llm._responses = ["partial"] * 20 + ["combined summary"]
    graph = build_summarization_graph(llm)

    result = await graph.ainvoke(
        _base_state(document_text=long_text), config=_thread_config()
    )

    assert result["structure_profile"]["strategy"] == "map_reduce"
    assert result["status"] == "success"

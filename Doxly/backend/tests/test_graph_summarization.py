import uuid

from app.ai.graphs.summarization import (
    MAP_REDUCE_TOKEN_THRESHOLD,
    SUMMARY_TYPE_INSTRUCTIONS,
    QualityCheckResult,
    build_summarization_graph,
    content_analyzer_node,
    quality_checker_node,
    summary_generator_node,
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


# --- R7 compatibility fix #1 — "bullet_points" matches api.md/database.md/
# the already-built frontend exactly (the pre-existing scaffolding said
# "bullet") ---


def test_summary_type_instructions_uses_bullet_points_not_bullet():
    assert "bullet_points" in SUMMARY_TYPE_INSTRUCTIONS
    assert "bullet" not in SUMMARY_TYPE_INSTRUCTIONS


async def test_graph_accepts_bullet_points_summary_type():
    llm = FakeLLMProvider(
        responses=["- point one\n- point two"],
        structured_responses=[QualityCheckResult(passed=True)],
    )
    graph = build_summarization_graph(llm)

    result = await graph.ainvoke(
        _base_state(summary_type="bullet_points"), config=_thread_config()
    )

    assert result["status"] == "success"
    assert result["draft_summary"] == "- point one\n- point two"


# --- R7 compatibility fix #2 (ai.md §4 / NFR-SEC-007) — prompt-injection
# defense: document-provided content must be explicitly delimited and
# framed as untrusted data, mirroring document_qa.py's SYSTEM_PROMPT
# pattern exactly, the same fix R6 already applied to comparison.py. These
# inspect the actual constructed system prompt/message via
# FakeLLMProvider.calls — not merely that the node runs successfully. ---


async def test_summary_generator_single_pass_prompt_disregards_embedded_instructions():
    llm = FakeLLMProvider(responses=["A concise summary."])

    await summary_generator_node(
        _base_state(structure_profile={"token_count": 10, "strategy": "single_pass"}),
        llm,
    )

    call = llm.calls[-1]
    assert "<document_context>" in call["messages"][0].content
    assert "</document_context>" in call["messages"][0].content
    system_prompt = call["system_prompt"]
    assert "reference data" in system_prompt
    assert "never instructions" in system_prompt
    assert "disregard" in system_prompt.lower()


async def test_summary_generator_map_reduce_prompt_disregards_embedded_instructions():
    long_text = (
        "This document discusses quarterly revenue growth in great detail. " * 400
    )
    llm = FakeLLMProvider(responses=["partial"] * 20 + ["combined"])

    await summary_generator_node(
        _base_state(
            document_text=long_text,
            structure_profile={"token_count": 999999, "strategy": "map_reduce"},
        ),
        llm,
    )

    # The per-chunk call (the first one made) must carry the same framing.
    chunk_call = llm.calls[0]
    assert "<document_context>" in chunk_call["messages"][0].content
    assert "</document_context>" in chunk_call["messages"][0].content
    assert "disregard" in chunk_call["system_prompt"].lower()


async def test_quality_checker_prompt_disregards_embedded_instructions():
    llm = FakeLLMProvider(structured_responses=[QualityCheckResult(passed=True)])

    await quality_checker_node(_base_state(draft_summary="A concise summary."), llm)

    call = llm.calls[-1]
    assert "<document_context>" in call["messages"][0].content
    assert "</document_context>" in call["messages"][0].content
    system_prompt = call["system_prompt"]
    assert "reference data" in system_prompt
    assert "never instructions" in system_prompt
    assert "disregard" in system_prompt.lower()

"""
`ObservedLLMProvider` (`app/ai/observed_llm_provider.py`) — the shared
per-call `ai_requests` logging wrapper first built for R6 (Comparison) and
reused by R7 (Summarization). Tested directly here (real Postgres via
`db_session`, real `AiRequestRepository`, a scripted `FakeLLMProvider`)
since it is now a shared unit on its own, not only exercised indirectly
through either caller's own test suite.
"""

from pydantic import BaseModel
from sqlalchemy import select

from app.ai.llm import FakeLLMProvider, Message, StructuredOutputError
from app.ai.observed_llm_provider import ObservedLLMProvider
from app.models.observability import AiRequest
from app.repositories.observability_repository import AiRequestRepository
from tests.conftest import make_user


class _Foo(BaseModel):
    x: int = 1


async def _rows_for(db_session, user_id) -> list[AiRequest]:
    return list(
        (
            await db_session.execute(
                select(AiRequest).where(AiRequest.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )


async def test_generate_success_logs_one_row_with_real_usage(db_session):
    user = await make_user(db_session)
    inner = FakeLLMProvider(responses=["a real response"])
    provider = ObservedLLMProvider(
        inner, AiRequestRepository(db_session), user.id, operation="summarization"
    )

    completion = await provider.generate(
        [Message("user", "hello there")], system_prompt="sys", model_tier="standard"
    )

    assert completion.text == "a real response"
    rows = await _rows_for(db_session, user.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.operation == "summarization"
    assert row.provider == "fake"
    assert row.model == "fake-standard"
    assert row.status == "success"
    assert row.error_code is None
    assert row.input_tokens == completion.input_tokens
    assert row.output_tokens == completion.output_tokens
    assert row.input_tokens > 0
    assert row.output_tokens > 0
    assert isinstance(row.latency_ms, int)


async def test_generate_failure_logs_an_error_row_without_fabricating_usage(
    db_session,
):
    user = await make_user(db_session)

    class _BrokenProvider(FakeLLMProvider):
        async def generate(self, *args, **kwargs):
            raise RuntimeError("provider unavailable")

    provider = ObservedLLMProvider(
        _BrokenProvider(),
        AiRequestRepository(db_session),
        user.id,
        operation="comparison",
    )

    try:
        await provider.generate(
            [Message("user", "hi")], system_prompt="sys", model_tier="standard"
        )
        raise AssertionError("expected generate() to raise")
    except RuntimeError:
        pass

    rows = await _rows_for(db_session, user.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.operation == "comparison"
    assert row.status == "error"
    assert row.error_code == "generation_failed"
    assert row.input_tokens is None
    assert row.output_tokens is None
    assert row.model == "n/a"


async def test_generate_structured_success_logs_real_usage(db_session):
    user = await make_user(db_session)
    inner = FakeLLMProvider(structured_responses=[_Foo(x=42)])
    provider = ObservedLLMProvider(
        inner, AiRequestRepository(db_session), user.id, operation="summarization"
    )

    completion = await provider.generate_structured(
        [Message("user", "hi")],
        system_prompt="sys",
        output_schema=_Foo,
        model_tier="fast",
    )

    assert completion.result.x == 42
    rows = await _rows_for(db_session, user.id)
    assert len(rows) == 1
    assert rows[0].status == "success"
    assert rows[0].input_tokens == completion.input_tokens
    assert rows[0].output_tokens == completion.output_tokens


async def test_generate_structured_failure_preserves_real_usage_when_available(
    db_session,
):
    """When the underlying exception already carries usage (e.g.
    AnthropicLLMProvider's structural-failure-after-a-successful-HTTP-call
    case), the logged row must use it, never re-fabricate or drop it."""
    user = await make_user(db_session)
    inner = FakeLLMProvider(
        structured_responses=[
            StructuredOutputError(
                "bad payload", input_tokens=42, output_tokens=7, model="claude-sonnet-5"
            )
        ]
    )
    provider = ObservedLLMProvider(
        inner, AiRequestRepository(db_session), user.id, operation="summarization"
    )

    try:
        await provider.generate_structured(
            [Message("user", "hi")],
            system_prompt="sys",
            output_schema=_Foo,
            model_tier="fast",
        )
        raise AssertionError("expected generate_structured() to raise")
    except StructuredOutputError:
        pass

    rows = await _rows_for(db_session, user.id)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "error"
    assert row.error_code == "structured_output_failed"
    assert row.input_tokens == 42
    assert row.output_tokens == 7
    assert row.model == "claude-sonnet-5"


async def test_ai_request_logging_failure_does_not_affect_the_wrapped_call(db_session):
    user = await make_user(db_session)
    inner = FakeLLMProvider(responses=["a real response"])

    class _FailingAiRequestRepository(AiRequestRepository):
        async def create(self, user_id, **fields):
            raise RuntimeError("observability store unavailable")

    provider = ObservedLLMProvider(
        inner, _FailingAiRequestRepository(db_session), user.id, operation="comparison"
    )

    completion = await provider.generate(
        [Message("user", "hi")], system_prompt="sys", model_tier="standard"
    )

    assert (
        completion.text == "a real response"
    )  # must not raise/propagate the logging failure

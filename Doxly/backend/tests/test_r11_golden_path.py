"""
tasks/remediation-plan.md R11 — Full System Integration. Drives the actual
P0 golden path (register -> login -> upload -> process -> search -> chat ->
summarize -> extract -> compare -> analytics) through the real ASGI app,
real committed Postgres, real Redis/RQ enqueue, and real (directly-invoked,
mirroring test_*_worker.py's own established pattern) worker job bodies --
not the SAVEPOINT-rollback `client`/`db_session` fixtures every other test
file uses, and not mocked CSRF/rate-limiting. This is deliberately the one
test file in the suite that exercises the full stack with nothing
overridden except the LLM provider (for determinism/cost, same as every
other AI-invoking test in this suite).

Real commits + `asyncio.run` per phase mirrors
test_document_processing_worker.py's own documented rationale: RQ job
entrypoints are plain sync functions with their own internal
`asyncio.run()`, which cannot be invoked from an already-running loop and
cannot safely share a connection opened on a different one. Every phase
that calls a worker job body directly is wrapped in the same
engine-dispose guard that file established.
"""

import asyncio
import uuid
from urllib.parse import urlparse

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.ai.graphs.comparison import ClassifiedDifferences
from app.ai.graphs.extraction import (
    PRESET_TEMPLATES,
    ExtractedField,
    _build_result_model,
)
from app.ai.graphs.summarization import QualityCheckResult
from app.ai.llm import FakeLLMProvider, get_llm_provider
from app.core.database import async_session_factory, engine
from app.core.queue import (
    get_comparison_queue,
    get_document_processing_queue,
    get_extraction_queue,
    get_summary_queue,
)
from app.main import app
from app.models import (
    AiRequest,
    Comparison,
    Conversation,
    Document,
    DocumentChunk,
    DocumentSummary,
    Extraction,
    User,
)
from app.workers import comparison_worker, extraction_worker, summary_worker
from app.workers.comparison_worker import run_comparison_job
from app.workers.document_processing_worker import process_document_job
from app.workers.extraction_worker import run_extraction_job
from app.workers.summary_worker import run_summary_job

REVENUE_DOC = (
    "Quarterly revenue grew twelve percent year over year according to the report."
)
GROUNDED_ANSWER = "Revenue grew twelve percent year over year."
INVOICE_A_DOC = "The invoice total is $100."
INVOICE_B_DOC = "The invoice total is $150."


def _reset_cross_loop_clients() -> None:
    """
    `_run`'s docstring covers asyncpg's cross-loop hazard; the real
    `rate_limit_general`/`rate_limit_ai` dependencies (deliberately not
    overridden in this file, unlike every other test's `client` fixture)
    hit `core/rate_limit.py`'s module-level `redis.asyncio.Redis` client,
    which has the identical hazard: its connection pool binds to whichever
    loop first used it, and a later `asyncio.run()` call in this file (a
    fresh loop each time) crashes reusing it ("Future attached to a
    different loop"). A *graceful* `.disconnect()` doesn't work either --
    it awaits the old (dead-loop) connection's own close-waiter, hitting
    the identical cross-loop error one level deeper. The safe fix is to
    just replace the module-level client (and its bound Lua script
    handle) with a fresh one, synchronously, never touching the old
    connection at all -- its socket is simply garbage-collected, which is
    fine for test infrastructure. `core/rate_limit.py`'s functions look up
    `redis_client`/`_token_bucket_script` as module globals at call time,
    so reassigning the module's attributes (not a local import binding)
    takes effect for every subsequent call in this process.
    """
    import redis.asyncio as redis_asyncio

    import app.core.chat_stream_control as chat_stream_control_module
    import app.core.rate_limit as rate_limit_module
    from app.core.config import settings

    fresh_client = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
    rate_limit_module.redis_client = fresh_client
    rate_limit_module._token_bucket_script = fresh_client.register_script(
        rate_limit_module._TOKEN_BUCKET_SCRIPT
    )
    # `auth_throttle` is a singleton constructed at import time as
    # `AuthThrottle(redis_client)` -- it captured the *old* client object by
    # reference, and other modules import `auth_throttle` itself (not
    # `rate_limit_module.auth_throttle`), so reassigning the module-level
    # name above wouldn't reach it. Mutating its `_client` attribute in
    # place is what actually takes effect everywhere it's already imported.
    rate_limit_module.auth_throttle._client = fresh_client
    # A third, independent module-level client: core/chat_stream_control.py
    # (ADR-024's stop/regenerate signal transport), used directly by the
    # chat SSE endpoint on every turn -- same cross-loop hazard, same fix.
    chat_stream_control_module.redis_client = redis_asyncio.from_url(
        settings.redis_url, decode_responses=True
    )


def _run(coro):
    """See test_document_processing_worker.py's `_run` for the full
    rationale. Every httpx call in this file that touches the DB goes
    through this, in phases, so the loop it runs on is disposed cleanly
    before/after each direct worker-job invocation below."""

    async def _wrapped():
        await engine.dispose()
        _reset_cross_loop_clients()
        result = await coro
        # The chat SSE endpoint's StreamingResponse runs its send loop in an
        # anyio TaskGroup; under the full suite's load that background task
        # can still be unwinding when this coroutine returns, and disposing
        # the engine/loop out from under it produces a spurious cross-loop
        # RuntimeError during its own cleanup (harmless -- the response was
        # already fully consumed -- but noisy and, rarely, disruptive to a
        # test running immediately after). A couple of scheduler ticks lets
        # it finish settling before this loop closes.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await engine.dispose()
        _reset_cross_loop_clients()
        return result

    return asyncio.run(_wrapped())


def _dispose_engine_before_and_after_sync_entrypoint_call():
    class _Guard:
        def __enter__(self):
            asyncio.run(engine.dispose())
            return self

        def __exit__(self, *exc_info):
            asyncio.run(engine.dispose())
            return False

    return _Guard()


def _path_of(url: str) -> str:
    return urlparse(url).path


def _csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token, "no csrf_token cookie set on this client -- was login real?"
    return {"X-CSRF-Token": token}


async def _register_and_login(client: AsyncClient, *, email: str) -> uuid.UUID:
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse9", "display_name": "R11 QA"},
    )
    assert register.status_code == 201, register.text
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correcthorse9"}
    )
    assert login.status_code == 200, login.text
    return uuid.UUID(login.json()["id"])


async def _upload_and_confirm(
    client: AsyncClient, content: str, *, file_name: str
) -> str:
    data = content.encode()
    presign = await client.post(
        "/api/v1/documents/presign",
        json={
            "file_name": file_name,
            "mime_type": "text/plain",
            "size_bytes": len(data),
        },
        headers=_csrf_headers(client),
    )
    assert presign.status_code == 201, presign.text
    body = presign.json()
    put_response = await client.put(_path_of(body["upload_url"]), content=data)
    assert put_response.status_code == 200
    confirm = await client.post(
        f"/api/v1/documents/{body['document_id']}/confirm",
        headers=_csrf_headers(client),
    )
    assert confirm.status_code == 202, confirm.text
    return body["document_id"]


async def _cleanup(*user_ids: uuid.UUID) -> None:
    async with async_session_factory() as session:
        for user_id in user_ids:
            await session.execute(delete(AiRequest).where(AiRequest.user_id == user_id))
            await session.execute(
                delete(DocumentSummary).where(DocumentSummary.user_id == user_id)
            )
            await session.execute(
                delete(Extraction).where(Extraction.user_id == user_id)
            )
            await session.execute(
                delete(Comparison).where(Comparison.user_id == user_id)
            )
            await session.execute(
                delete(Conversation).where(Conversation.user_id == user_id)
            )
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.user_id == user_id)
            )
            await session.execute(delete(Document).where(Document.user_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


def _invoice_result_model():
    result_model = _build_result_model(PRESET_TEMPLATES["invoice"]["fields"])
    return result_model(
        invoice_number=ExtractedField(value="123", confidence=0.9, source_page=1),
        invoice_date=ExtractedField(value="2026-01-01", confidence=0.9, source_page=1),
        vendor_name=ExtractedField(value="Acme Corp", confidence=0.9, source_page=1),
        total_amount=ExtractedField(value="500", confidence=0.9, source_page=1),
        due_date=ExtractedField(value=None, found=False, reason="not mentioned"),
    )


async def _parse_sse(response) -> list[tuple[str, dict]]:
    import json

    events: list[tuple[str, dict]] = []
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk
        while "\n\n" in buffer:
            raw_event, buffer = buffer.split("\n\n", 1)
            event_name = None
            data: dict = {}
            for line in raw_event.splitlines():
                if line.startswith("event: "):
                    event_name = line[len("event: ") :]
                elif line.startswith("data: "):
                    data = json.loads(line[len("data: ") :])
            if event_name is not None:
                events.append((event_name, data))
    return events


def test_golden_path_end_to_end(monkeypatch):
    email_a = f"r11-a-{uuid.uuid4()}@example.com"
    email_b = f"r11-b-{uuid.uuid4()}@example.com"
    user_a_id = user_b_id = None

    try:
        # === Phase 1: register/login both users, upload three documents for A ===
        async def _phase1():
            nonlocal user_a_id, user_b_id
            client_a = AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            )
            client_b = AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            )
            async with client_a, client_b:
                user_a_id = await _register_and_login(client_a, email=email_a)
                user_b_id = await _register_and_login(client_b, email=email_b)

                # --- A: Authentication -> Document Management (checklist A) ---
                # A fresh, cookie-less client is the real "unauthenticated" check.
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as anon:
                    unauth = await anon.get("/api/v1/documents")
                assert unauth.status_code == 401
                assert unauth.json()["error"]["code"] == "unauthorized"

                docs_queue_before = get_document_processing_queue().count
                doc1_id = await _upload_and_confirm(
                    client_a, REVENUE_DOC, file_name="revenue.txt"
                )
                doc2_id = await _upload_and_confirm(
                    client_a, INVOICE_A_DOC, file_name="invoice_a.txt"
                )
                doc3_id = await _upload_and_confirm(
                    client_a, INVOICE_B_DOC, file_name="invoice_b.txt"
                )

                return doc1_id, doc2_id, doc3_id, docs_queue_before

        doc1_id, doc2_id, doc3_id, docs_queue_before = _run(_phase1())
        doc1_id, doc2_id, doc3_id = (
            uuid.UUID(doc1_id),
            uuid.UUID(doc2_id),
            uuid.UUID(doc3_id),
        )

        # === Real RQ enqueue happened (checklist M) ===
        assert get_document_processing_queue().count >= docs_queue_before + 3

        # === Phase 2: real worker processes all three documents (checklist B) ===
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            process_document_job(str(user_a_id), str(doc1_id))
            process_document_job(str(user_a_id), str(doc2_id))
            process_document_job(str(user_a_id), str(doc3_id))

        # === Phase 3: verify processed state, search, chat, create summary/extraction/comparison ===
        async def _phase3():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client_a, AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client_b:
                await client_a.post(
                    "/api/v1/auth/login",
                    json={"email": email_a, "password": "correcthorse9"},
                )
                await client_b.post(
                    "/api/v1/auth/login",
                    json={"email": email_b, "password": "correcthorse9"},
                )

                # --- B: processing completion produces expected chunks/metadata ---
                detail = await client_a.get(f"/api/v1/documents/{doc1_id}")
                assert detail.status_code == 200
                assert detail.json()["status"] == "ready"
                assert detail.json()["extracted_text_available"] is True

                # --- C: Processing -> Search, tenant-scoped ---
                search_a = await client_a.get(
                    "/api/v1/search", params={"q": "revenue grew twelve percent"}
                )
                assert search_a.status_code == 200
                assert search_a.json()["total"] >= 1
                assert any(
                    item["document_id"] == str(doc1_id)
                    for item in search_a.json()["items"]
                )
                search_b = await client_b.get(
                    "/api/v1/search", params={"q": "revenue grew twelve percent"}
                )
                assert search_b.status_code == 200
                assert search_b.json()["items"] == []

                # --- D: Processing -> Chat, SSE contract, citations, tenant isolation ---
                # document_qa.py's graph entry point is the intent classifier
                # (langgraph.md §2 node 1) -- it makes its own real LLM call
                # before retrieval ever runs, so the first queued response is
                # consumed by *it*, not the answer. Two responses queued,
                # exactly mirroring test_chat_sse.py's own proven pattern.
                monkeypatch.setitem(
                    app.dependency_overrides,
                    get_llm_provider,
                    lambda: FakeLLMProvider(responses=["factual_qa", GROUNDED_ANSWER]),
                )
                conv = await client_a.post(
                    "/api/v1/chat/conversations",
                    json={"document_ids": [str(doc1_id)]},
                    headers=_csrf_headers(client_a),
                )
                assert conv.status_code == 201, conv.text
                conversation_id = conv.json()["id"]

                async with client_a.stream(
                    "POST",
                    f"/api/v1/chat/conversations/{conversation_id}/messages",
                    json={"content": "revenue grew twelve percent year over year"},
                    headers=_csrf_headers(client_a),
                ) as stream_response:
                    assert stream_response.status_code == 200
                    events = await _parse_sse(stream_response)
                event_names = [name for name, _ in events]
                assert event_names[0] == "message_id"
                assert event_names[-1] == "done"
                assert "citations" in event_names
                citations_event = next(
                    data for name, data in events if name == "citations"
                )
                assert citations_event["citations"][0]["document_id"] == str(doc1_id)

                conv_cross_tenant = await client_b.get(
                    f"/api/v1/chat/conversations/{conversation_id}"
                )
                assert conv_cross_tenant.status_code == 404

                # --- G: Processing -> Summarization ---
                summary_create = await client_a.post(
                    f"/api/v1/documents/{doc1_id}/summaries",
                    json={"summary_type": "brief"},
                    headers=_csrf_headers(client_a),
                )
                assert summary_create.status_code == 202, summary_create.text
                summary_id = summary_create.json()["id"]

                # --- E: Processing -> Extraction ---
                extraction_create = await client_a.post(
                    "/api/v1/extractions",
                    json={"document_id": str(doc1_id), "template_key": "invoice"},
                    headers=_csrf_headers(client_a),
                )
                assert extraction_create.status_code == 202, extraction_create.text
                extraction_id = extraction_create.json()["id"]

                # --- F: Processing -> Comparison ---
                # (the cross-tenant-rejection variant is exercised in Phase 5,
                # once a real document id owned by user B exists to test against)
                comparison_create = await client_a.post(
                    "/api/v1/comparisons",
                    json={"document_a_id": str(doc2_id), "document_b_id": str(doc3_id)},
                    headers=_csrf_headers(client_a),
                )
                assert comparison_create.status_code == 202, comparison_create.text
                comparison_id = comparison_create.json()["id"]

                return summary_id, extraction_id, comparison_id, conversation_id

        summary_id, extraction_id, comparison_id, conversation_id = _run(_phase3())
        app.dependency_overrides.pop(get_llm_provider, None)

        # === Real RQ enqueue for each AI domain (checklist M) ===
        assert get_summary_queue().count >= 1
        assert get_extraction_queue().count >= 1
        assert get_comparison_queue().count >= 1

        # === Phase 4: real workers process summary/extraction/comparison ===
        monkeypatch.setattr(
            summary_worker,
            "get_llm_provider",
            lambda: FakeLLMProvider(
                responses=["A concise summary of the report."],
                structured_responses=[QualityCheckResult(passed=True)],
            ),
        )
        monkeypatch.setattr(
            extraction_worker,
            "get_llm_provider",
            lambda: FakeLLMProvider(
                responses=["invoice"], structured_responses=[_invoice_result_model()]
            ),
        )
        monkeypatch.setattr(
            comparison_worker,
            "get_llm_provider",
            lambda: FakeLLMProvider(
                responses=["The total changed from $100 to $150."],
                structured_responses=[ClassifiedDifferences(categories=["numeric"])],
            ),
        )
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_summary_job(str(user_a_id), str(summary_id))
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_extraction_job(str(user_a_id), str(extraction_id))
        with _dispose_engine_before_and_after_sync_entrypoint_call():
            run_comparison_job(str(user_a_id), str(comparison_id))

        # === Phase 5: verify terminal states, cross-tenant 404s everywhere,
        #     analytics reflects real activity, admin surface works ===
        async def _phase5():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client_a, AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client_b:
                await client_a.post(
                    "/api/v1/auth/login",
                    json={"email": email_a, "password": "correcthorse9"},
                )
                await client_b.post(
                    "/api/v1/auth/login",
                    json={"email": email_b, "password": "correcthorse9"},
                )

                summary = await client_a.get(f"/api/v1/summaries/{summary_id}")
                assert summary.status_code == 200
                assert summary.json()["status"] == "completed"
                assert summary.json()["content"] == "A concise summary of the report."

                extraction = await client_a.get(f"/api/v1/extractions/{extraction_id}")
                assert extraction.status_code == 200
                assert extraction.json()["status"] == "completed"

                comparison = await client_a.get(f"/api/v1/comparisons/{comparison_id}")
                assert comparison.status_code == 200
                assert comparison.json()["status"] == "completed"
                assert (
                    comparison.json()["result"]["modifications"][0]["change_type"]
                    == "numeric"
                )

                # --- H/K: cross-tenant 404s across every domain, not just one ---
                for path in (
                    f"/api/v1/documents/{doc1_id}",
                    f"/api/v1/summaries/{summary_id}",
                    f"/api/v1/extractions/{extraction_id}",
                    f"/api/v1/comparisons/{comparison_id}",
                    f"/api/v1/chat/conversations/{conversation_id}",
                ):
                    response = await client_b.get(path)
                    assert (
                        response.status_code == 404
                    ), f"{path} -> {response.status_code}"
                    assert response.json()["error"]["code"] == "not_found"

                # --- F: cross-tenant document in a comparison request also 404s ---
                foreign_doc = await _upload_and_confirm(
                    client_b, "b's own document", file_name="b.txt"
                )
                cross_tenant_compare = await client_a.post(
                    "/api/v1/comparisons",
                    json={"document_a_id": str(doc1_id), "document_b_id": foreign_doc},
                    headers=_csrf_headers(client_a),
                )
                assert cross_tenant_compare.status_code == 404
                assert cross_tenant_compare.json()["error"]["code"] == "not_found"

                # --- I: Analytics reflects real activity, tenant-isolated ---
                analytics_a = await client_a.get("/api/v1/analytics/dashboard")
                assert analytics_a.status_code == 200
                body_a = analytics_a.json()
                assert body_a["documents_processed"] >= 3
                assert body_a["ai_requests"] >= 1
                feature_names = {f["feature"] for f in body_a["most_used_features"]}
                assert feature_names & {
                    "chat",
                    "summarization",
                    "extraction",
                    "comparison",
                }

                analytics_b = await client_b.get("/api/v1/analytics/dashboard")
                assert analytics_b.status_code == 200
                body_b = analytics_b.json()
                # b's one upload above was never processed by a worker (stays
                # "queued") -- documents_processed counts only status="ready".
                assert body_b["documents_processed"] == 0
                assert not (
                    {"chat", "summarization", "extraction", "comparison"}
                    & {f["feature"] for f in body_b["most_used_features"]}
                )

                # --- L: no cross-tenant leakage in ai_requests (observability) ---
                # B's own search above (search_b) legitimately logs one real
                # "embedding" row (R8, the query-embedding call) -- that's B's
                # own activity, not a leak. The actual isolation property is
                # that none of A's chat/summarization/extraction/comparison
                # operations ever attach to B's user_id.
                async with async_session_factory() as session:
                    from sqlalchemy import select as sa_select

                    rows = (
                        (
                            await session.execute(
                                sa_select(AiRequest).where(
                                    AiRequest.user_id == user_b_id
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    assert {r.operation for r in rows} <= {"embedding"}
                    assert not any(
                        r.operation
                        in {"chat", "summarization", "extraction", "comparison"}
                        for r in rows
                    )

                # --- J: Admin -- promote a real admin, verify against real data ---
                async with async_session_factory() as session:
                    from sqlalchemy import update as sa_update

                    await session.execute(
                        sa_update(User).where(User.id == user_a_id).values(role="admin")
                    )
                    await session.commit()

                admin_reauth = AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                )
                async with admin_reauth:
                    await admin_reauth.post(
                        "/api/v1/auth/login",
                        json={"email": email_a, "password": "correcthorse9"},
                    )
                    admin_users = await admin_reauth.get("/api/v1/admin/users")
                    assert admin_users.status_code == 200
                    emails = {item["email"] for item in admin_users.json()["items"]}
                    assert email_a in emails and email_b in emails

                    non_admin_denied = await client_b.get("/api/v1/admin/users")
                    assert non_admin_denied.status_code == 403

                    suspend = await admin_reauth.post(
                        f"/api/v1/admin/users/{user_b_id}/suspend",
                        json={"reason": "R11 integration check"},
                        headers=_csrf_headers(admin_reauth),
                    )
                    assert suspend.status_code == 200

                    b_next_request = await client_b.get("/api/v1/users/me")
                    assert b_next_request.status_code == 403
                    assert b_next_request.json()["error"]["code"] == "account_suspended"

                    unsuspend = await admin_reauth.post(
                        f"/api/v1/admin/users/{user_b_id}/unsuspend",
                        headers=_csrf_headers(admin_reauth),
                    )
                    assert unsuspend.status_code == 200

                    b_restored = await client_b.get("/api/v1/users/me")
                    assert b_restored.status_code == 200

        _run(_phase5())

    finally:
        app.dependency_overrides.pop(get_llm_provider, None)
        if user_a_id is not None or user_b_id is not None:
            _run(_cleanup(*(uid for uid in (user_a_id, user_b_id) if uid is not None)))


def test_failed_processing_is_reflected_correctly_across_the_system():
    """
    Checklist item B ("failure states behave according to the
    specification") -- a document that fails processing (rag.md §2's
    degenerate zero-chunk case: whitespace-only content) must surface
    status="failed" with a user-safe processing_error via the real API,
    and every AI-invoking domain must reject it with 409
    document_not_ready, not silently accept a non-ready document.
    """
    email = f"r11-fail-{uuid.uuid4()}@example.com"
    user_id = None

    try:

        async def _phase1():
            nonlocal user_id
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                user_id = await _register_and_login(client, email=email)
                doc_id = await _upload_and_confirm(
                    client, "   \n\t  ", file_name="blank.txt"
                )
                return doc_id

        doc_id = uuid.UUID(_run(_phase1()))

        with _dispose_engine_before_and_after_sync_entrypoint_call():
            process_document_job(str(user_id), str(doc_id))

        async def _phase2():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": "correcthorse9"},
                )

                detail = await client.get(f"/api/v1/documents/{doc_id}")
                assert detail.status_code == 200
                assert detail.json()["status"] == "failed"
                assert detail.json()["processing_error"]

                summary_attempt = await client.post(
                    f"/api/v1/documents/{doc_id}/summaries",
                    json={"summary_type": "brief"},
                    headers=_csrf_headers(client),
                )
                assert summary_attempt.status_code == 409
                assert summary_attempt.json()["error"]["code"] == "document_not_ready"

                extraction_attempt = await client.post(
                    "/api/v1/extractions",
                    json={"document_id": str(doc_id), "template_key": "invoice"},
                    headers=_csrf_headers(client),
                )
                assert extraction_attempt.status_code == 409
                assert (
                    extraction_attempt.json()["error"]["code"] == "document_not_ready"
                )

                # ChatService.create_conversation itself validates document
                # readiness up front -- a not-ready document is rejected at
                # conversation-creation time, not deferred to message-send.
                conv_attempt = await client.post(
                    "/api/v1/chat/conversations",
                    json={"document_ids": [str(doc_id)]},
                    headers=_csrf_headers(client),
                )
                assert conv_attempt.status_code == 409
                assert conv_attempt.json()["error"]["code"] == "document_not_ready"

        _run(_phase2())

    finally:
        if user_id is not None:
            _run(_cleanup(user_id))

"""
tasks/remediation-plan.md R12 (Production Deployment Readiness §15's named
"scripted smoke test" deliverable) -- drives the P0 golden path
(tasks/remediation-plan.md §15.1) against a **live, separately-running**
FastAPI process, talking to it over a real socket (real HTTP, real
Postgres, real Redis, real RQ enqueue).

This is a different verification tier than tests/test_r11_golden_path.py,
not a duplicate of it: that file drives the same golden path in-process via
httpx's ASGITransport -- no real network hop, no real separate OS process
for the API. This script starts `uvicorn` as a real subprocess -- the
actual production entrypoint (backend/Dockerfile's CMD) -- and only ever
talks to it the way a real client would. It exists specifically to catch
the class of bug that only shows up at a real process boundary.

**Known, deliberate gap: no real `rq worker` process.** An earlier version
of this script also started a real `rq worker` subprocess (docker-compose.
yml's `worker` command) and hit two independent POSIX-only crashes running
it natively on a Windows host: `os.fork()` (RQ's default `Worker` forks a
child per job) and `signal.SIGALRM` (RQ's job-timeout "death penalty"
mechanism, invoked on *every* job execution, not just timeouts). Neither
API exists on Windows -- this is an upstream RQ constraint, not a Doxly
defect, and does not affect the real deployment (backend/Dockerfile is a
Linux container, where both exist). But it means a real, separately-
running `rq worker` process consuming the queue has, as of R12, never
actually been exercised anywhere in this project: not by this script, not
by any pytest file (test_*_worker.py and test_r11_golden_path.py both
invoke job functions directly, matching this script below), and not by CI
(no workflow step runs `rq worker`, on any OS). This script instead
verifies the enqueue side for real (asserting each RQ queue's `.count`
increments after the API call that should enqueue it) and then invokes
the job function directly in-process -- the same, established pattern
every worker test file already uses -- to actually execute it. See the
R12 readiness report for this gap's full writeup; it is not silently
glossed over here.

Usage:
    python scripts/smoke_test.py

Requires a reachable Postgres and Redis at DATABASE_URL/REDIS_URL (defaults
to the same local dev values app/core/config.py itself defaults to) with
migrations already applied (`alembic upgrade head`). Never point this at a
real production DATABASE_URL/REDIS_URL -- it creates and deletes real rows
under real, if disposable, test accounts.

Exit code 0 on full success, 1 on any failed step (with the failing step
named on stderr) -- suitable for a CI/runbook gate, not just interactive use.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from typing import Any

import httpx

HOST = "127.0.0.1"
PORT = 8931
BASE_URL = f"http://{HOST}:{PORT}"
STARTUP_TIMEOUT_S = 30

REVENUE_DOC = (
    "Quarterly revenue grew twelve percent year over year according to the report."
)
INVOICE_A_DOC = "The invoice total is $100."
INVOICE_B_DOC = "The invoice total is $150."

_passed: list[str] = []
_failed: list[tuple[str, str]] = []


def _check(step: str, condition: bool, detail: str = "") -> None:
    if condition:
        _passed.append(step)
        print(f"  [PASS] {step}")
    else:
        _failed.append((step, detail))
        print(f"  [FAIL] {step} -- {detail}")


@contextmanager
def _live_api_process():
    """Starts a real `uvicorn` subprocess -- backend/Dockerfile's actual
    CMD -- and tears it down on exit.

    Output is redirected to a log file, never `subprocess.PIPE` left
    undrained: uvicorn logs one line per request (`request_context_
    middleware`'s own structured log plus uvicorn's own access log), and
    this script alone makes 100+ requests -- easily enough to fill the OS
    pipe buffer (~64KB) if nothing reads it, which blocks the subprocess's
    next write() and silently deadlocks this entire script. Found by an
    earlier real run of this exact script hanging forever with zero
    output, not by reasoning about it in the abstract."""
    log_dir = tempfile.mkdtemp(prefix="doxly-smoke-")
    api_log_path = os.path.join(log_dir, "uvicorn.log")
    print(f"Subprocess log: {api_log_path}")

    with open(api_log_path, "w") as api_log:
        api_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                HOST,
                "--port",
                str(PORT),
            ],
            stdout=api_log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT_S
            healthy = False
            while time.monotonic() < deadline:
                if api_proc.poll() is not None:
                    with open(api_log_path) as f:
                        raise RuntimeError(f"uvicorn exited early:\n{f.read()}")
                try:
                    resp = httpx.get(f"{BASE_URL}/health", timeout=2)
                    if resp.status_code == 200:
                        healthy = True
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
            if not healthy:
                raise RuntimeError(
                    f"/health never returned 200 within {STARTUP_TIMEOUT_S}s"
                )
            yield api_proc
        finally:
            api_proc.terminate()
            try:
                api_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(
                    "  uvicorn did not exit on SIGTERM within 10s -- killing",
                    file=sys.stderr,
                )
                api_proc.kill()
                api_proc.wait(timeout=5)


def _run_job_in_process(job_fn: Any, *args: str) -> None:
    """Executes an RQ job function directly, synchronously, in this
    process -- see the module docstring's "Known, deliberate gap" section
    for why this replaces a real `rq worker` consumer here. Matches
    test_*_worker.py's own established `_dispose_engine_before_and_after_
    sync_entrypoint_call` pattern: `app.core.database.engine`'s connection
    pool is a process-wide singleton, and each job function's own internal
    `asyncio.run()` is a fresh event loop -- disposing the pool immediately
    before and after prevents a connection created on this script's own
    asyncio.run() calls (cleanup/promote, below) from leaking into a job's
    different loop, or vice versa."""
    import asyncio

    from app.core.database import engine

    asyncio.run(engine.dispose())
    try:
        job_fn(*args)
    finally:
        asyncio.run(engine.dispose())


def _csrf_headers(client: httpx.Client) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    return {"X-CSRF-Token": token} if token else {}


def _register_and_login(client: httpx.Client, email: str) -> str | None:
    register = client.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": email,
            "password": "correcthorse9",
            "display_name": "Smoke Test",
        },
    )
    if register.status_code != 201:
        return None
    login = client.post(
        f"{BASE_URL}/api/v1/auth/login",
        json={"email": email, "password": "correcthorse9"},
    )
    if login.status_code != 200:
        return None
    return login.json()["id"]


def _upload_and_confirm(
    client: httpx.Client, content: str, file_name: str
) -> str | None:
    data = content.encode()
    presign = client.post(
        f"{BASE_URL}/api/v1/documents/presign",
        json={
            "file_name": file_name,
            "mime_type": "text/plain",
            "size_bytes": len(data),
        },
        headers=_csrf_headers(client),
    )
    if presign.status_code != 201:
        return None
    body = presign.json()
    put_resp = client.put(
        f"{BASE_URL}{httpx.URL(body['upload_url']).path}", content=data
    )
    if put_resp.status_code != 200:
        return None
    confirm = client.post(
        f"{BASE_URL}/api/v1/documents/{body['document_id']}/confirm",
        headers=_csrf_headers(client),
    )
    if confirm.status_code != 202:
        return None
    return body["document_id"]


def _parse_sse_sync(response: httpx.Response) -> list[tuple[str, dict]]:
    """Same event-frame parsing as test_r11_golden_path.py's async
    `_parse_sse`, over httpx's sync streaming iterator instead."""
    import json

    events: list[tuple[str, dict]] = []
    buffer = ""
    for chunk in response.iter_text():
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


def _cleanup(user_ids: list[str]) -> None:
    """Best-effort: real teardown via the ORM directly (no DELETE-account
    endpoint exists yet -- FR-EXPORT-004/account deletion is unowned per
    remediation-plan.md §16.2), matching test_r11_golden_path.py's own
    cleanup pattern so this script never leaves smoke-test rows behind in
    a shared dev database."""
    import asyncio

    from sqlalchemy import delete

    from app.core.database import async_session_factory, engine
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

    async def _run() -> None:
        async with async_session_factory() as session:
            for uid in user_ids:
                user_id = uuid.UUID(uid)
                for model in (
                    AiRequest,
                    DocumentSummary,
                    Extraction,
                    Comparison,
                    Conversation,
                    DocumentChunk,
                    Document,
                ):
                    await session.execute(delete(model).where(model.user_id == user_id))
                await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await engine.dispose()

    asyncio.run(_run())


def main() -> int:
    print(f"Starting live uvicorn against {BASE_URL} ...")
    with _live_api_process():
        print("API process healthy. Driving P0 golden path over real HTTP...\n")

        email_a = f"smoke-a-{uuid.uuid4()}@example.com"
        email_b = f"smoke-b-{uuid.uuid4()}@example.com"
        user_ids: list[str] = []

        try:
            with httpx.Client() as anon:
                unauth = anon.get(f"{BASE_URL}/api/v1/documents")
                _check(
                    "unauthenticated request rejected (401)",
                    unauth.status_code == 401,
                    f"got {unauth.status_code}",
                )

            client_a = httpx.Client()
            client_b = httpx.Client()

            user_a_id = _register_and_login(client_a, email_a)
            _check("user A register+login", user_a_id is not None)
            if user_a_id:
                user_ids.append(user_a_id)

            user_b_id = _register_and_login(client_b, email_b)
            _check("user B register+login", user_b_id is not None)
            if user_b_id:
                user_ids.append(user_b_id)

            if not (user_a_id and user_b_id):
                print(
                    "\nCannot continue without both users -- aborting remaining steps."
                )
                return _summarize()

            from app.core.queue import get_document_processing_queue
            from app.workers.document_processing_worker import process_document_job

            queue_count_before = get_document_processing_queue().count
            doc1_id = _upload_and_confirm(client_a, REVENUE_DOC, "revenue.txt")
            doc2_id = _upload_and_confirm(client_a, INVOICE_A_DOC, "invoice_a.txt")
            doc3_id = _upload_and_confirm(client_a, INVOICE_B_DOC, "invoice_b.txt")
            _check("document upload + confirm (x3)", all((doc1_id, doc2_id, doc3_id)))

            if not (doc1_id and doc2_id and doc3_id):
                print("\nCannot continue without uploaded documents -- aborting.")
                return _summarize()

            _check(
                "confirm-upload really enqueued to RQ (queue.count += 3)",
                get_document_processing_queue().count >= queue_count_before + 3,
            )

            # No real `rq worker` process on this host (module docstring's
            # "Known, deliberate gap") -- executes the job function directly,
            # the same pattern test_document_processing_worker.py and
            # test_r11_golden_path.py already use.
            _run_job_in_process(process_document_job, user_a_id, doc1_id)
            _run_job_in_process(process_document_job, user_a_id, doc2_id)
            _run_job_in_process(process_document_job, user_a_id, doc3_id)
            processed = client_a.get(f"{BASE_URL}/api/v1/documents/{doc1_id}").json()
            _check(
                "document processing job produced status=ready",
                processed.get("status") == "ready",
                f"final status={processed.get('status')}",
            )

            search_a = client_a.get(
                f"{BASE_URL}/api/v1/search", params={"q": "revenue grew twelve percent"}
            )
            _check(
                "search returns owner's own document",
                search_a.status_code == 200
                and any(
                    item["document_id"] == doc1_id
                    for item in search_a.json().get("items", [])
                ),
                f"status={search_a.status_code} body={search_a.text[:200]}",
            )
            search_b = client_b.get(
                f"{BASE_URL}/api/v1/search", params={"q": "revenue grew twelve percent"}
            )
            _check(
                "search is tenant-isolated (other user sees nothing)",
                search_b.status_code == 200 and search_b.json().get("items") == [],
                f"status={search_b.status_code} body={search_b.text[:200]}",
            )

            conv = client_a.post(
                f"{BASE_URL}/api/v1/chat/conversations",
                json={"document_ids": [doc1_id]},
                headers=_csrf_headers(client_a),
            )
            _check(
                "chat conversation created (201)",
                conv.status_code == 201,
                conv.text[:200],
            )
            if conv.status_code == 201:
                conversation_id = conv.json()["id"]
                with client_a.stream(
                    "POST",
                    f"{BASE_URL}/api/v1/chat/conversations/{conversation_id}/messages",
                    json={"content": "What was the revenue growth?"},
                    headers=_csrf_headers(client_a),
                ) as stream_response:
                    sse_status = stream_response.status_code
                    events = _parse_sse_sync(stream_response)
                event_names = [name for name, _ in events]
                _check(
                    "chat SSE contract (message_id first, done last, citations present)",
                    sse_status == 200
                    and event_names[:1] == ["message_id"]
                    and event_names[-1:] == ["done"]
                    and "citations" in event_names,
                    f"status={sse_status} events={event_names}",
                )

            summary_create = client_a.post(
                f"{BASE_URL}/api/v1/documents/{doc1_id}/summaries",
                json={"summary_type": "brief"},
                headers=_csrf_headers(client_a),
            )
            _check(
                "summarization enqueued (202)",
                summary_create.status_code == 202,
                summary_create.text[:200],
            )
            extraction_create = client_a.post(
                f"{BASE_URL}/api/v1/extractions",
                json={"document_id": doc1_id, "template_key": "invoice"},
                headers=_csrf_headers(client_a),
            )
            _check(
                "extraction enqueued (202)",
                extraction_create.status_code == 202,
                extraction_create.text[:200],
            )
            comparison_create = client_a.post(
                f"{BASE_URL}/api/v1/comparisons",
                json={"document_a_id": doc2_id, "document_b_id": doc3_id},
                headers=_csrf_headers(client_a),
            )
            _check(
                "comparison enqueued (202)",
                comparison_create.status_code == 202,
                comparison_create.text[:200],
            )

            # Summarization/extraction/comparison all reach the LLM through
            # generate_structured, and FakeLLMProvider's default (no queued
            # structured_responses) *raises* rather than returning something
            # harmless (app/ai/llm.py) -- this process's own module-level
            # get_llm_provider is monkeypatched per worker module the same
            # way test_r11_golden_path.py does it, since this script runs
            # these job functions directly, in-process (module docstring).
            from app.ai.graphs.comparison import ClassifiedDifferences
            from app.ai.graphs.extraction import (
                PRESET_TEMPLATES,
                ExtractedField,
                _build_result_model,
            )
            from app.ai.graphs.summarization import QualityCheckResult
            from app.ai.llm import FakeLLMProvider
            from app.workers import comparison_worker, extraction_worker, summary_worker
            from app.workers.comparison_worker import run_comparison_job
            from app.workers.extraction_worker import run_extraction_job
            from app.workers.summary_worker import run_summary_job

            if summary_create.status_code == 202:
                summary_id = summary_create.json()["id"]
                summary_worker.get_llm_provider = lambda: FakeLLMProvider(
                    responses=["A concise summary of the report."],
                    structured_responses=[QualityCheckResult(passed=True)],
                )
                _run_job_in_process(run_summary_job, user_a_id, summary_id)
                result = client_a.get(
                    f"{BASE_URL}/api/v1/summaries/{summary_id}"
                ).json()
                _check(
                    "in-process job completed summarization",
                    result.get("status") == "completed",
                    f"final status={result.get('status')}",
                )

            if extraction_create.status_code == 202:
                extraction_id = extraction_create.json()["id"]
                result_model = _build_result_model(
                    PRESET_TEMPLATES["invoice"]["fields"]
                )
                invoice_result = result_model(
                    invoice_number=ExtractedField(
                        value="123", confidence=0.9, source_page=1
                    ),
                    invoice_date=ExtractedField(
                        value="2026-01-01", confidence=0.9, source_page=1
                    ),
                    vendor_name=ExtractedField(
                        value="Acme Corp", confidence=0.9, source_page=1
                    ),
                    total_amount=ExtractedField(
                        value="500", confidence=0.9, source_page=1
                    ),
                    due_date=ExtractedField(
                        value=None, found=False, reason="not mentioned"
                    ),
                )
                extraction_worker.get_llm_provider = lambda: FakeLLMProvider(
                    responses=["invoice"], structured_responses=[invoice_result]
                )
                _run_job_in_process(run_extraction_job, user_a_id, extraction_id)
                result = client_a.get(
                    f"{BASE_URL}/api/v1/extractions/{extraction_id}"
                ).json()
                _check(
                    "in-process job completed extraction",
                    result.get("status") == "completed",
                    f"final status={result.get('status')}",
                )

            if comparison_create.status_code == 202:
                comparison_id = comparison_create.json()["id"]
                comparison_worker.get_llm_provider = lambda: FakeLLMProvider(
                    responses=["The total changed from $100 to $150."],
                    structured_responses=[
                        ClassifiedDifferences(categories=["numeric"])
                    ],
                )
                _run_job_in_process(run_comparison_job, user_a_id, comparison_id)
                result = client_a.get(
                    f"{BASE_URL}/api/v1/comparisons/{comparison_id}"
                ).json()
                _check(
                    "in-process job completed comparison",
                    result.get("status") == "completed",
                    f"final status={result.get('status')}",
                )

            cross_tenant = client_b.get(f"{BASE_URL}/api/v1/documents/{doc1_id}")
            _check(
                "cross-tenant document access returns 404, not 403",
                cross_tenant.status_code == 404,
                f"got {cross_tenant.status_code}",
            )

            # --- Admin: promote user A directly via DB, verify suspend/unsuspend ---
            import asyncio

            from sqlalchemy import update as sa_update

            from app.core.database import async_session_factory, engine
            from app.models import User

            async def _promote(uid: str) -> None:
                async with async_session_factory() as session:
                    await session.execute(
                        sa_update(User)
                        .where(User.id == uuid.UUID(uid))
                        .values(role="admin")
                    )
                    await session.commit()
                await engine.dispose()

            asyncio.run(_promote(user_a_id))
            admin_client = httpx.Client()
            admin_login = admin_client.post(
                f"{BASE_URL}/api/v1/auth/login",
                json={"email": email_a, "password": "correcthorse9"},
            )
            _check(
                "admin re-login after role promotion", admin_login.status_code == 200
            )

            admin_users = admin_client.get(f"{BASE_URL}/api/v1/admin/users")
            _check(
                "admin can list users",
                admin_users.status_code == 200,
                admin_users.text[:200],
            )

            non_admin_denied = client_b.get(f"{BASE_URL}/api/v1/admin/users")
            _check(
                "non-admin denied admin route (403)",
                non_admin_denied.status_code == 403,
            )

            suspend = admin_client.post(
                f"{BASE_URL}/api/v1/admin/users/{user_b_id}/suspend",
                json={"reason": "smoke test"},
                headers=_csrf_headers(admin_client),
            )
            _check(
                "admin suspend succeeds", suspend.status_code == 200, suspend.text[:200]
            )

            b_next = client_b.get(f"{BASE_URL}/api/v1/users/me")
            _check(
                "suspended user immediately rejected (no re-login needed)",
                b_next.status_code == 403
                and b_next.json().get("error", {}).get("code") == "account_suspended",
                f"status={b_next.status_code} body={b_next.text[:200]}",
            )

            unsuspend = admin_client.post(
                f"{BASE_URL}/api/v1/admin/users/{user_b_id}/unsuspend",
                headers=_csrf_headers(admin_client),
            )
            _check("admin unsuspend succeeds", unsuspend.status_code == 200)

            # --- Rate limiting: hammer the general tier past its bucket ---
            # A *fresh* user, not user_a -- user_a's bucket already absorbed
            # ~20 real requests earlier in this run (uploads, chat, summary/
            # extraction/comparison, admin actions), making the exact
            # remaining-token count hard to reason about precisely. A never-
            # before-used identity starts its bucket at the full documented
            # capacity (api.md §0.7: 60/min), so 75 rapid requests
            # deterministically cross it -- confirmed against a real live
            # run: exactly 60 succeed, then every request 429s.
            burst_client = httpx.Client()
            burst_email = f"smoke-burst-{uuid.uuid4()}@example.com"
            burst_user_id = _register_and_login(burst_client, burst_email)
            if burst_user_id:
                user_ids.append(burst_user_id)
            statuses = [
                burst_client.get(f"{BASE_URL}/api/v1/documents").status_code
                for _ in range(75)
            ]
            _check(
                "general rate limit engages under burst (429 seen)",
                429 in statuses,
                f"no 429 in {len(statuses)} rapid requests",
            )

            # --- Error envelope: a deliberately invalid request ---
            bad_request = client_a.get(f"{BASE_URL}/api/v1/documents/not-a-real-uuid")
            _check(
                "error envelope shape on a client error",
                bad_request.status_code in (404, 422)
                and "error" in bad_request.json()
                and {"code", "message"} <= set(bad_request.json()["error"].keys()),
                f"status={bad_request.status_code} body={bad_request.text[:200]}",
            )
            _check(
                "X-Request-ID present on error response",
                "x-request-id" in {k.lower() for k in bad_request.headers},
            )

            for client in (client_a, client_b, admin_client, burst_client):
                client.close()

        finally:
            if user_ids:
                print(f"\nCleaning up {len(user_ids)} smoke-test user(s)...")
                # Best-effort teardown -- a cleanup failure must never mask
                # the actual smoke-test result already collected above.
                try:
                    _cleanup(user_ids)
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"  cleanup failed (non-fatal, manual cleanup may be needed): {exc}",
                        file=sys.stderr,
                    )

    return _summarize()


def _summarize() -> int:
    print(f"\n{'=' * 60}")
    print(f"PASSED: {len(_passed)}   FAILED: {len(_failed)}")
    if _failed:
        print("\nFailed steps:")
        for step, detail in _failed:
            print(f"  - {step}: {detail}")
        return 1
    print("All smoke-test steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

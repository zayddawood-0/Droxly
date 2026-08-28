"""
tasks/remediation-plan.md R12 (Production Deployment Readiness §15's named
"basic load test against performance.md's existing budgets" deliverable).

Deliberately minimal: no new dependency is added (httpx is already a
project dependency, per pyproject.toml's LLM/EmbeddingProvider clients) --
`skills/backend.md`'s "unnecessary dependencies" rule applies to a
one-off verification script exactly as much as to application code. This
is not a substitute for a real load-testing tool (k6/Locust) against a
seeded, production-scale dataset; it is the "basic" check the remediation
plan actually asked for: concurrent requests against a live process,
compared to the documented budget.

Targets `NFR-PERF-002` (performance.md §3): non-AI CRUD reads/writes
respond within 300ms p95. Run against the same live `uvicorn` process
scripts/smoke_test.py starts (start it separately first, or run this
after smoke_test.py's own server is up) -- this script does not manage
the server process itself, so it can be pointed at any already-running
instance via BASE_URL.

Usage:
    python scripts/load_test.py [base_url] [concurrency] [requests_per_worker]
"""

from __future__ import annotations

import statistics
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8931"
DEFAULT_CONCURRENCY = 10
DEFAULT_REQUESTS_PER_WORKER = 20
BUDGET_P95_MS = 300  # performance.md NFR-PERF-002


def _register_authenticated_client(base_url: str) -> httpx.Client:
    client = httpx.Client(base_url=base_url, timeout=10)
    email = f"load-{uuid.uuid4()}@example.com"
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correcthorse9", "display_name": "Load Test"},
    )
    client.post(
        "/api/v1/auth/login", json={"email": email, "password": "correcthorse9"}
    )
    return client


def _worker(base_url: str, path: str, n_requests: int) -> list[float]:
    client = _register_authenticated_client(base_url)
    durations_ms: list[float] = []
    try:
        for _ in range(n_requests):
            start = time.perf_counter()
            client.get(path)
            durations_ms.append((time.perf_counter() - start) * 1000)
    finally:
        client.close()
    return durations_ms


def run(base_url: str, concurrency: int, requests_per_worker: int) -> int:
    # A representative non-AI CRUD read (api.md's paginated document list) --
    # exactly the endpoint category NFR-PERF-002's budget names.
    path = "/api/v1/documents"

    print(
        f"Load test: {concurrency} concurrent clients x {requests_per_worker} "
        f"requests each against {base_url}{path}"
    )
    print(f"Budget (performance.md NFR-PERF-002): p95 <= {BUDGET_P95_MS}ms\n")

    all_durations: list[float] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_worker, base_url, path, requests_per_worker)
            for _ in range(concurrency)
        ]
        for future in as_completed(futures):
            all_durations.extend(future.result())

    all_durations.sort()
    n = len(all_durations)
    if n == 0:
        print("No requests completed -- is the server running?", file=sys.stderr)
        return 1

    p50 = all_durations[int(n * 0.50)]
    p95 = all_durations[min(int(n * 0.95), n - 1)]
    p99 = all_durations[min(int(n * 0.99), n - 1)]
    mean = statistics.mean(all_durations)

    print(f"Requests completed: {n}")
    print(f"  mean: {mean:.1f}ms")
    print(f"  p50:  {p50:.1f}ms")
    print(f"  p95:  {p95:.1f}ms")
    print(f"  p99:  {p99:.1f}ms")

    within_budget = p95 <= BUDGET_P95_MS
    print(
        f"\n{'PASS' if within_budget else 'FAIL'}: p95 {p95:.1f}ms "
        f"{'<=' if within_budget else '>'} {BUDGET_P95_MS}ms budget"
    )
    return 0 if within_budget else 1


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    concurrency = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_CONCURRENCY
    requests_per_worker = (
        int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_REQUESTS_PER_WORKER
    )
    sys.exit(run(base_url, concurrency, requests_per_worker))

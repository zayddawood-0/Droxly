# Doxly — Testing Engineering Skill

> How to write good tests for Doxly. `specs/testing.md` is authoritative for *what* must be tested and the requirement-to-test traceability — this file is craft: fixture patterns, mocking idioms, naming, and the judgment calls that make a test suite fast and trustworthy rather than slow and flaky.

## Purpose

A document-intelligence product handling untrusted uploads and cross-user data lives or dies on tests that actually catch tenant-isolation and grounding bugs — not just line coverage. This file exists so every contributor writes tests that pull their weight.

## Unit Testing

- **Purpose:** fast, deterministic verification of a single unit of logic in isolation.
- **Project-specific usage:** frontend pure functions/utilities (Vitest), backend service-layer logic with repositories mocked (pytest), individual LangGraph nodes with the LLM mocked at the `LLMProvider` boundary (`skills/ai-engineering.md`).
- **Best practices:** mock at the abstraction boundary (the `LLMProvider`/repository interface), never at the vendor SDK or SQL level — this keeps tests stable across implementation changes; one behavior per test, named after the behavior (`test_login_rejects_unverified_email`, not `test_login_2`).
- **Common mistakes:** a "unit" test that actually hits a real database or network call (that's an integration/API test — mislabeling it hides which layer a failure is in); over-mocking to the point the test no longer exercises real logic.
- **Quality expectations:** runs in milliseconds, no network, no shared state between tests (fresh fixtures every test, no test-order dependency).

## Integration Testing

- **Purpose:** verify that layers compose correctly without the cost of a full browser or a real LLM call.
- **Project-specific usage:** frontend page/feature flows against a mocked network layer (MSW, `specs/testing.md` §1.3); backend service+repository wiring against a real test Postgres instance (not mocked — query correctness is exactly what a mock can't catch).
- **Best practices:** for backend integration tests, use a real (test) database with transactional rollback per test (or a fresh schema per test run) so tests are isolated without needing hand-written cleanup code; for frontend, intercept at the network boundary (MSW) rather than mocking `fetch` directly, so the test exercises the same request-construction code path as production.
- **Common mistakes:** sharing one seeded database state across many tests without isolation, causing order-dependent flakiness; mocking so much of the stack that the test degrades into a unit test with extra ceremony.
- **Quality expectations:** deterministic and re-runnable in any order; a failure points clearly at which layer-boundary broke.

## API Testing

- **Purpose:** verify the actual HTTP contract defined in `specs/api.md`.
- **Project-specific usage:** `httpx.AsyncClient` against the FastAPI app (in-process, no real network hop) per `specs/testing.md` §2.2 — every documented endpoint gets a happy path, a validation-failure (422), an unauthenticated (401), and, where applicable, an authorization-failure test.
- **Best practices:** assert the full response body shape against the documented schema, not just the status code — this is what catches accidental field over-exposure; build a small authenticated-client test fixture (a helper that registers/logs in a throwaway user and returns a client with cookies set) so every test doesn't hand-roll auth setup.
- **Common mistakes:** testing only the 200 path and skipping the error/authorization paths, which is exactly where tenant-isolation bugs hide; asserting on a partial response shape that would pass even if the endpoint leaked an extra field.
- **Quality expectations:** every endpoint in `specs/api.md` has API-test coverage before its feature is considered done — no endpoint ships "to be tested later."

## Component Testing

- **Purpose:** verify individual React components render and behave correctly, including accessibility.
- **Project-specific usage:** React Testing Library, querying by role/label/text — never by CSS class or internal state (`specs/testing.md` §1.2). Priority: auth forms, upload dropzone, chat message bubble with citations, extraction result table, document viewer.
- **Best practices:** write assertions the way a screen reader or keyboard-only user would experience the component — this incidentally verifies `NFR-A11Y-001` as a side effect of normal testing rather than a separate audit pass.
- **Common mistakes:** snapshot-testing entire component trees as the primary assertion strategy (brittle, doesn't express intent); testing implementation details (hook internals, prop names) that break on harmless refactors.
- **Quality expectations:** a component's four UI states required by `specs/ui-ux.md` (loading/empty/error/success) each have at least one test.

## E2E Testing

- **Purpose:** catch integration bugs that lower layers structurally cannot see.
- **Project-specific usage:** Playwright, against a real backend in a test environment, covering the golden path (register → upload → chat → extract → compare → search) and a handful of critical secondary flows (`specs/testing.md` §1.4).
- **Best practices:** select elements by `data-testid` or accessible role, never brittle CSS selectors that break on a styling change; keep the suite small and stable — E2E is the most expensive, flakiest layer, so it earns its place only for flows that genuinely span the full stack, not as a substitute for missing unit/API coverage.
- **Common mistakes:** adding a new E2E test for a bug that a unit or API test would have caught faster and more reliably; letting E2E flakiness go unaddressed until the suite is ignored/skipped by habit.
- **Quality expectations:** the E2E suite is green and trusted enough that a failure is always investigated, never dismissed as "probably flaky."

## AI Evaluation

- **Purpose:** grade AI output quality, which isn't binary pass/fail the way deterministic code is.
- **Project-specific usage:** the golden-set regression methodology (`specs/testing.md` §3.7) — structural/semantic assertions (does the answer cite a real, relevant chunk? does the extracted field match the expected value or correctly return `not_found`?) rather than exact-string matching, which is too brittle for LLM output.
- **Best practices:** grow the golden set from real production issues, not just synthetic cases dreamed up in advance; keep evaluation assertions checking the *property* that matters (grounded, correctly declined, correctly classified) rather than the literal wording.
- **Common mistakes:** asserting exact output text and then loosening the assertion (or skipping the test) the first time a harmless wording change breaks it, which erodes the suite's value over time.
- **Quality expectations:** every prompt/model/chunking change is gated on this suite before it ships (`specs/testing.md` §4).

## RAG Evaluation

- **Purpose:** verify retrieval quality specifically, separate from generation quality.
- **Project-specific usage:** precision checks against a golden document+query set, tenant-scoping checks (a near-duplicate chunk under a different user must never leak), threshold-behavior checks (`specs/testing.md` §3.2).
- **Best practices:** always include at least one adversarial tenant-isolation case per new retrieval code path — the case where the *most* semantically similar chunk in the whole table belongs to another user, and assert it's still excluded.
- **Common mistakes:** only testing retrieval quality with single-tenant fixtures, which can't catch a missing `user_id` filter.
- **Quality expectations:** every new retrieval code path ships with a tenant-scoping test, no exceptions.

## Security Testing

- **Purpose:** verify the controls defined in `specs/security.md` actually hold, not just that they're described.
- **Project-specific usage:** the cross-tenant access suite (`specs/testing.md` §2.5, the highest-priority backend test category), file-upload validation tests (MIME sniffing, size limits, path-traversal-resistant storage keys), rate-limit tests, prompt-injection adversarial tests (`specs/testing.md` §3.6).
- **Best practices:** write the cross-tenant test *at the same time* as the feature that introduces a new tenant-scoped resource, not as a follow-up — treat it as part of the feature's definition of done.
- **Common mistakes:** testing authorization only at the API layer and assuming the repository layer is "obviously" also scoped correctly — test both, since the repository layer is the actual enforcement point (`specs/architecture.md` §6).
- **Quality expectations:** the cross-tenant suite is release-blocking; a failure here blocks merge regardless of what else passes.

## Regression Testing

- **Purpose:** prevent a fixed bug from coming back.
- **Project-specific usage:** any bug found in production or code review gets a regression test added in the same PR that fixes it, covering both deterministic code (a unit/API/integration test reproducing the exact failure) and AI quality (a new golden-set case if the bug was a grounding/citation/extraction-quality issue).
- **Best practices:** name the regression test after the bug/scenario it prevents, not generically, so its purpose survives long after the original incident is forgotten.
- **Common mistakes:** fixing a bug without a test, relying on "we'll remember not to do that again."
- **Quality expectations:** every production incident retro includes "was there a missing test, and has it been added?" as a required question.

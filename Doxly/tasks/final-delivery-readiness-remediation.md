# Final Delivery-Readiness Remediation Pass

**Date:** 2026-08-29 · **Scope:** the 5 conditions raised by `tasks/final-release-audit.md` · **No R13 created.**

---

## 1. Executive Verdict

## **READY WITH CONDITIONS**

Priority 1 (the one actual code defect — `confirm_upload` idempotency) is fixed, tested, and verified: 520/520 backend tests (517 + 3 new), run twice, deterministic; the fix required no migration. Priority 3 (Playwright) turned out to be **not actually environment-blocked** — independent verification found the earlier "no browser" conclusion conflated the `claude-in-chrome` interactive MCP tool (genuinely unavailable) with Playwright's own bundled, already-installed Chromium (fully functional here) — 58/59 real E2E tests pass. Priorities 2 (OQ-13) and 4 (standalone Linux `rq worker`) remain genuinely open: both require something this session cannot provide (a human platform decision with billing implications; a working Docker daemon or Linux CI runner), confirmed by direct re-investigation, not assumed from the prior audit.

Nothing found in this pass blocks release on its own. What keeps this from a clean **READY** is unchanged in kind from the prior audit, but the RECORD is now more accurate: OQ-13 still needs your decision, a real Linux `rq worker` run is still unverified in this session, and one pre-existing, backend-unrelated frontend E2E flake was found and is reported (not fixed, per your instruction not to touch E2E tests).

---

## 2. Changes Actually Made

**Priority 1 only — nothing else was touched.**

1. `backend/app/repositories/document_repository.py` — added `DocumentRepository.confirm_if_unconfirmed`, an atomic, tenant-scoped, guarded `UPDATE ... WHERE checksum_sha256 = ''` (with `.returning(Document)`) that lets exactly one caller "win" a confirm, even under real concurrent duplicate requests.
2. `backend/app/services/document_service.py` — `confirm_upload` now: (a) fast-path-returns an already-confirmed document without re-touching storage/quota; (b) otherwise verifies/checksums as before, then calls the atomic guard; (c) only increments `storage_used_bytes`/enqueues processing if the guard's UPDATE actually matched a row; (d) returns the existing confirmed document, untouched, if it lost a race.
3. `backend/tests/test_documents_api.py` — 2 new tests: repeated sequential confirm doesn't double-count usage; a second user's usage is untouched by the first user's repeat confirm.
4. `backend/tests/test_confirm_upload_concurrency.py` — **new file** — a dedicated test proving the atomic guard is safe under a *genuine* concurrent duplicate (two real, independently-committing sessions racing via `asyncio.gather`), deliberately not using the shared `client`/`db_session` fixtures (they bind every session in a test to one already-open connection/transaction, which cannot exercise real cross-transaction locking).
5. `tasks/R3-document-processing.md` — updated to record finding #3 as closed, with the exact fix, verification results, and file scope (matching that file's own established remediation-log pattern).

No other source file was touched. No frontend file was touched. No migration was added (see §7). No new dependency was added.

---

## 3. Confirmed Remaining Blockers

Re-investigated independently, not carried forward from the prior audit on trust:

1. **`decisions.md` OQ-13 (container platform)** — confirmed still open by re-reading the ADR directly. It requires provisioning a real account (Fly.io, Railway, or AWS ECS/Fargate) with real billing implications — something no spec, code change, or CI workflow file can resolve on its own. `ADR-007`/`OQ-13` already name Fly.io as the *recommended default*, not a decision; no `fly.toml`/`railway.json`/ECS config exists anywhere in the repo (confirmed by search), and `.github/workflows/ci.yml`'s `deploy` job is a documented no-op until `FLY_API_TOKEN` (or the Railway equivalent) is provisioned as a secret. **This is exactly the shape of decision the user's own instructions say I must not make unilaterally** — left open, exact decision needed below (§8).
2. **A real, standalone `rq worker` process on Linux has never been exercised** in this session or, as far as this repository's history shows, anywhere in this project. See §9 for the full investigation.

## 4. Environment-Blocked Verification Items

1. **Standalone Linux `rq worker` smoke test** — blocked because the Docker daemon remained unresponsive throughout this session (reconfirmed via a fresh 10-second `docker info` probe at the start of this pass — identical symptom to the prior audit, not a new or different failure).
2. That's the only remaining environment-blocked item. **Playwright E2E is no longer blocked** — see §10.

## 5. Test/Lint/Type/Build Results

| Check | Result |
|---|---|
| Backend `pytest`, targeted (confirm_upload fix) | 69 passed |
| Backend `pytest`, full suite | **520 passed**, run 2× this pass, identical both times |
| Backend `ruff check` (app/, tests/, scripts/) | Clean |
| Backend `black --check` | Clean, 169 files |
| Backend `mypy app/` | Clean, 102 files |
| Migration verification | `alembic heads` == `current` == `0004_search_tsvector` (unchanged) |
| Frontend `tsc --noEmit` | Clean |
| Frontend `eslint` | Clean |
| Frontend production build | Confirmed via Playwright's own `webServer` (`npm run build && npm run start`) succeeding as part of the E2E run below |
| Frontend `vitest` | Not re-run this pass (no frontend source changed since the last full green run in `tasks/final-release-audit.md`) |
| Playwright E2E (`npx playwright test`) | **58/59 passed** — see §10 for the one failure |
| Live-local smoke test (`backend/scripts/smoke_test.py`) | **26/26 passed**, run after the confirm_upload fix, unaffected as expected |

---

## 6. Exact Files Changed

```
 M backend/app/repositories/document_repository.py
 M backend/app/services/document_service.py
 M backend/tests/test_documents_api.py
 M tasks/R3-document-processing.md
?? backend/tests/test_confirm_upload_concurrency.py
?? tasks/final-release-audit.md          (from the PRIOR turn's audit — still uncommitted, untouched this pass)
?? tasks/final-delivery-readiness-remediation.md   (this report)
```

`git status` confirms no other file changed. No R1/R4–R12 file, no frontend file, no spec file (`requirements.md`/`api.md`/`database.md`/`architecture.md`/`security.md`/`observability.md`), and no `roadmap.md` was modified.

---

## 7. Whether a Migration Is Required

**No.** `presign_upload` already writes `checksum_sha256=""` as a real sentinel at document-creation time (a genuine sha256 hex digest is always 64 characters, never empty) — this existing column already distinguishes "not yet confirmed" from "confirmed" with zero schema change. The fix is a repository-method addition plus a service-method restructure, nothing more. Verified: `alembic heads` == `current`, unchanged before and after this pass.

---

## 8. Whether OQ-13 Was Resolved or Remains Open

**Remains open — by design, not by omission.** I did not choose a platform. What I verified:

- `decisions.md`'s own text is explicit that this is an "action with real-world side effects (billing, a live deployment target) that requires a human with dashboard/billing access" — the same category as OQ-04's storage-provider account provisioning, which is also still open.
- Nothing else in the repository (Docker config, CI workflow, any spec file) implies a platform choice has secretly already been made anywhere — I checked for `fly.toml`, `railway.json`/`.toml`, and any ECS/Fargate config; none exist.
- There is no "smallest documentation-only resolution" I could respectably propose here: the recommended default (Fly.io) is already documented as a recommendation in `ADR-007`/`OQ-13`; writing that recommendation into `fly.toml` as if it were a decision would be choosing the platform, which you explicitly told me not to do.

**The exact decision you need to make:** which container platform hosts the backend/worker containers — Fly.io, Railway, or AWS ECS/Fargate (or another) — and then provision that platform's account, project, region, and the corresponding CI secret (`FLY_API_TOKEN` or equivalent). Once you tell me which one, the smallest next step is writing that platform's config file and wiring the CI secret name into the already-conditional `deploy` job — no other code change is needed.

---

## 9. Whether Standalone RQ Worker Verification Was Completed

**Not completed — genuinely environment-blocked, not faked.** What I did verify, by direct code/config inspection (not by running it):

- `backend/Dockerfile`'s base image is `python:3.12-slim` — a real Linux environment where both `os.fork()` (RQ's default `Worker` forks a child process per job) and `signal.SIGALRM` (RQ's job-timeout "death penalty" mechanism, invoked on every job execution) are standard, always-available POSIX APIs. Neither exists on Windows, which is exactly why this session's own earlier attempts crashed — confirmed by two independent tracebacks in `backend/scripts/smoke_test.py`'s git history/docstring, both `AttributeError`s naming the missing Windows API, not an application logic error.
- `docker-compose.yml`'s `worker` service invokes `rq worker document_processing extraction comparison summary --url redis://redis:6379` — RQ's **default** (forking) `Worker` class, the correct choice for the real Linux deployment target, not the `SimpleWorker` workaround this session's own Windows-only smoke test had to substitute.
- No Windows-specific code, platform guard, or conditional import exists anywhere in `app/workers/` or `app/core/queue.py` (grepped for `platform_system`/`sys.platform`/`win32` — zero matches) — the worker code itself is ordinary, portable Python with no hidden Windows dependency that would behave differently on Linux.
- Re-confirmed the Docker daemon is still unresponsive in this session (fresh `docker info` probe, 10s timeout, no response — identical symptom to the prior audit).

**What is required to actually close this gap:** either a working Docker daemon (on this host or another) to run `docker compose up worker` for real, or a Linux CI runner running the equivalent command — for example, a new nightly-workflow job (or an addition to the existing `ai-eval` job's `ubuntu-latest` runner, which already provisions Postgres) that starts a real Redis + `rq worker` process and drives one document through the full pipeline over the actual queue, not a direct in-process job-function call. I did not add this CI job myself — it's a real, if small, scope decision (new CI job, new runtime dependency in that job) outside this pass's five listed priorities, and you did not ask for a new CI workflow.

---

## 10. Whether Playwright E2E Was Completed

**Yes — and the prior audit's "environment-blocked" conclusion for this item was wrong, or at least incomplete. Corrected here, not carried forward.**

What actually happened: earlier sessions (R11/R12, and the prior release audit) checked for a browser via the `claude-in-chrome` MCP tool (`tabs_context_mcp`) and found none attached, concluding Playwright was environment-blocked. That tool controls an *interactive* browser extension — it has nothing to do with Playwright's own bundled browser binaries, which install and run completely independently. This pass checked directly: Playwright 1.62.1's Chromium (and headless-shell) were already installed on disk (`C:\Users\Home\AppData\Local\ms-playwright`, dated before this session), so `npx playwright test` was actually runnable here without any project-configuration change.

**Result:** `npx playwright test` (all 10 spec files, matching `.github/workflows/nightly.yml`'s exact invocation) — **58 of 59 tests passed**, using a real headless Chromium and a real Next.js production build+start (`playwright.config.ts`'s `webServer` block), against no live backend (the suite's own long-standing, documented design — see `nightly.yml`'s comment: these specs test the frontend's connectivity-error handling and route rendering, not a live golden path against a real API).

**The one failure**, found and reported, not fixed (your instruction: don't weaken/skip/delete/rewrite E2E tests):
- `route-smoke.spec.ts` › `route /analytics responds 200 with no console errors` — the `/analytics` route logs two browser-level `"Failed to load resource: ... 502 (Bad Gateway)"` console messages (from its own API calls failing against the unreachable backend) that this test's generic "zero console errors" assertion doesn't tolerate. Every other BFF-dependent route in the suite (`/dashboard`, `/documents`, `/chat`, `/compare`, `/search`, etc.) produces zero console errors under the identical no-backend condition, so this appears to be page-specific (likely the number/timing of parallel API calls the analytics page fires) rather than a suite-wide issue. **Not a security or correctness defect** — `analytics.spec.ts`'s own dedicated test (`"the analytics page shows a real connectivity error, not a blank dashboard"`) passes, confirming the page's actual user-facing behavior is correct; only this one generic smoke assertion is stricter than the page's real behavior warrants. Left untouched, exactly as instructed — flagged here for your awareness, not treated as a release blocker (it predates this pass and is unrelated to R1–R12 backend work).

---

## 11. Git Status and Commit Status

```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
	modified:   backend/app/repositories/document_repository.py
	modified:   backend/app/services/document_service.py
	modified:   backend/tests/test_documents_api.py
	modified:   tasks/R3-document-processing.md

Untracked files:
	backend/tests/test_confirm_upload_concurrency.py
	tasks/final-release-audit.md
	tasks/final-delivery-readiness-remediation.md
```

**No commit was made.** No push occurred. No deployment was performed or attempted. No R13 task was created (this report and its sibling audit are named without the `R`-prefix pattern specifically to avoid that appearance, matching the correction already applied to the prior audit report's own filename). No secret was added — the changed/new files were grepped for credential-shaped strings; none found. R1–R12 functionality remains green: the full backend suite (520/520, including every pre-existing R1–R12 test, unmodified in behavior) and the live-local smoke test (26/26) both pass after this pass's changes.

Awaiting your review before any commit, push, or further action.

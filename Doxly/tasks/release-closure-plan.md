# Doxly Release Closure Plan

**Date:** 2026-08-29 · **Scope:** planning/verification only — no code, spec, or task files modified; no commits; no deployment. Source of truth: `tasks/final-release-audit.md`, cross-checked against `remediation-plan.md`, `roadmap.md`, `requirements.md`, `api.md`, `testing.md`, `architecture.md`, `security.md`, `observability.md`, `decisions.md`, and every R1–R12 task file.

---

## Verified current state before planning

`git log` confirms the Priority-1 fix from the last pass (confirm_upload idempotency) and both audit reports are **already committed** (`51b986b docs(audit): add final release readiness report with conditions.` — one commit ahead of `origin/main`, not yet pushed). Working tree is clean. This changes one item's status from "open" to "resolved, needs no further action" relative to `final-release-audit.md`'s original list — reflected below.

One **new finding**, not previously surfaced this precisely: re-reading `testing.md` §2.4 alongside the actual Playwright output from the last pass shows the E2E suite is still running the **pre-backend "connectivity-error" substitute** `testing.md` itself calls "documented, temporary" — e.g. test names like *"sending a message on the real backend-less BFF surfaces the connectivity error"* — not the real golden-path suite `testing.md` says is "expected once a real backend exists for these domains." Backends have existed since R1–R11. This is a genuine, spec-acknowledged content gap in the E2E suite, distinct from (and more precise than) "no browser available" — see item 3 below.

---

## Release Closure Table

| # | Item | Source / requirement | Current status | Severity | Exact action required | Files likely changed | Code/spec/task change? | External infra needed? | Blocks production? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **OQ-13** — container/deployment platform choice | `decisions.md` OQ-13, `ADR-007` | **Intentionally open** — requires a human decision with billing implications; nothing in the repo secretly resolves it | N/A (not a defect) | You choose Fly.io / Railway / ECS-Fargate / other, then provision the account + region + the platform's CI secret (`FLY_API_TOKEN` or equivalent) | New: `fly.toml` or equivalent. Modified: none required beyond the CI secret being present (the conditional deploy step already exists in `ci.yml`) | Task/spec update to `decisions.md` (flip OQ-13 to Decided) once you choose | **Yes** — a real platform account | **Yes, for actual deployment.** Does not block R12's own code/config closure (see analysis below) |
| 2 | **Deployed-environment smoke test** | `remediation-plan.md` §15.1 P0 gate | **Environment-blocked** — no deployment exists | N/A | Run `backend/scripts/smoke_test.py` (adapted per `deployment.md` §14.3 to target a remote origin instead of spawning local subprocesses) against the real deployed origin | `backend/scripts/smoke_test.py` (small adaptation) | Minor code change to the script when the time comes | **Yes** — item 1 must resolve first | **Yes** — but strictly downstream of item 1, not independently actionable today |
| 3 | **Playwright E2E — can it run at all** | Prior audits' "no browser" conclusion | **Resolved, verified this session's prior pass** — Playwright's own bundled Chromium runs fine here (58/59 real tests passed); the earlier "blocked" conclusion conflated the separate `claude-in-chrome` interactive tool (genuinely unavailable) with Playwright itself | N/A | None — documentation-only: `final-release-audit.md`'s framing of this as "environment-blocked" should be understood as superseded by the later `final-delivery-readiness-remediation.md` finding, not re-litigated | None (or: a one-line correction in `final-release-audit.md` if you want the record self-consistent) | Documentation only, optional | No | No |
| 4 | **Playwright E2E — real golden-path content** | `testing.md` §2.4 ("the golden-path suite itself is expected once a real backend exists for these domains") | **Genuinely unresolved** — a real spec-anticipated upgrade that no R-task ever took ownership of, same shape as the Summarization phase-numbering gap `remediation-plan.md` §16 already caught once | MEDIUM | Rewrite (not delete) the 10 `frontend/e2e/*.spec.ts` files' scenarios to exercise the real backend (register → upload → chat → extract → compare → search) instead of the connectivity-error substitute — a real implementation task, not a "run and check" task | `frontend/e2e/*.spec.ts` (all 10), possibly `playwright.config.ts` (webServer needs a real backend+Postgres+Redis reachable, which this environment already has locally) | Yes — meaningful test-code rewrite | No — this environment already has everything needed (real Postgres/Redis reachable, real backend startable) | **No** — the golden path is already proven at the API level (R11's integration suite + this session's live-local smoke test); this closes a coverage gap, it doesn't fix a known-broken flow |
| 5 | **Standalone Linux `rq worker` verification** | `remediation-plan.md` R3/R12; never run anywhere in this project's history | **Environment-blocked** — Docker daemon unresponsive (reconfirmed, 10s probe); no Linux CI job exists that runs `rq worker` | MEDIUM (confidence gap, not a known defect — code inspection found no Windows-specific logic anywhere in the worker path) | Either fix/restart the local Docker daemon and run `docker compose up worker` for real, **or** add a Linux CI job (new `nightly.yml` job, `ubuntu-latest`, real Redis + `rq worker` + one document through the real queue) | New CI job in `.github/workflows/nightly.yml` (if you choose that route) | Yes, if you choose the CI-job route | Yes — a working Docker daemon (this host or another) **or** GitHub Actions | **No** — strongly believed correct by code inspection (standard RQ pattern, Linux base image, `os.fork()`/`SIGALRM` both standard on Linux); this raises confidence, doesn't fix a suspected bug |
| 6 | **R2 has no dedicated task file** | SDD convention (every other R-task has one) | **Confirmed still true** — cosmetic/paper-trail gap only | LOW/INFORMATIONAL | Create `tasks/R2-document-management.md` retroactively, documenting what's already built and tested (no new code) | New: `tasks/R2-document-management.md` | Task file only | No | No |
| 7 | **R2/R6 commit messages undersell scope** | Git hygiene | **Confirmed still true** (`33fd6e1`, `c9eabfa`-adjacent history) | LOW/INFORMATIONAL | **Recommend: leave as-is.** You explicitly said not to rewrite history unless absolutely necessary — this doesn't meet that bar (content is correct and complete, only the message is narrow) | None | None | No | No |
| 8 | **`confirm_upload` idempotency** | Self-disclosed, `tasks/R3-document-processing.md` finding #3 | **Already fixed and committed** (`51b986b`, this session's prior pass) — not P0/P1 per the remediation plan; R3's own task file explicitly says this and findings #4/#5 "do not, on their own, block R3's gate" | Was MEDIUM, now resolved | None — verify only: 520/520 backend tests (incl. 3 new), run twice deterministic; live-local smoke test 26/26 after the fix; no migration was needed | None further | None further | No | **No — and wasn't going to, even unfixed**, per R3's own explicit gate language |
| 9 | **Retry-count ambiguity** ("max 3 attempts" vs. RQ's 3-retries-=-4-attempts) | Self-disclosed, `tasks/R3-document-processing.md` finding #4 | **Still open** — needs a product decision on what "max 3 attempts" means before any code change is meaningful | MEDIUM | You decide the intended semantics; then a one-line `Retry(max=...)` change in `backend/app/core/queue.py` | `backend/app/core/queue.py`, possibly `specs/decisions.md` (a small ADR clarifying the reading) | Yes, once decided | No | No |
| 10 | **CSV column-count tolerance** ("beyond a tolerance" implemented as zero tolerance) | Self-disclosed, `tasks/R3-document-processing.md` finding #5 | **Still open** — needs a defined tolerance number before a code change is meaningful | LOW | You decide a tolerance number; then a small change in the CSV parser's validation | `backend/app/document_processing/csv_parser.py` | Yes, once decided | No | No |
| 11 | **Proxy/IP trust handling** (`_client_ip()` reads `request.client.host` directly, no `X-Forwarded-For` logic) | `final-release-audit.md` §4 | **Intentionally not-yet-needed** — no reverse proxy/ingress exists until item 1 (OQ-13) resolves | LOW | Once a platform is chosen and its ingress/load-balancer shape is known, add trusted-proxy header handling to `_client_ip()` | `backend/app/core/rate_limit.py` | Yes, once item 1 resolves | Depends on item 1 | No — not exploitable today (no proxy in the path) |
| 12 | **`ai_requests` cardinality inconsistency** (comparison logs per-call, chat/extraction log per-run) | `final-release-audit.md` §7 | **Working as designed, documented, not a defect** | INFORMATIONAL | None | None | None | No | No |
| 13 | **`.mypy_cache` not named in `backend/.gitignore`** | `final-release-audit.md` §13 | **Cosmetic** — already effectively ignored via mypy's own nested `.gitignore`, confirmed via `git status --ignored` | INFORMATIONAL | Optional: add `.mypy_cache/` to `backend/.gitignore` for clarity | `backend/.gitignore` | Trivial | No | No |

---

## A / B / C / D Categorization

**A — Must be completed before production**
- #1 OQ-13 (your decision — cannot be automated)
- #2 Deployed-environment smoke test (mechanically follows from #1; the script exists and is ready)

**B — Should be completed before production if environment allows**
- #4 Playwright E2E real golden-path rewrite (environment allows it *today*, in this session — a real implementation task, not environment-blocked; recommend before production but the golden path is already proven at the API level, so this is risk-reduction, not a gap in actual coverage)
- #5 Standalone Linux `rq worker` verification (environment does *not* currently allow it in this session — needs Docker or CI; strongly believed correct by inspection)

**C — Post-release / fast-follow**
- #9 Retry-count ambiguity (needs your product decision first; low real-world impact either way)
- #10 CSV tolerance number (needs your decision first; low impact)
- #11 Proxy/IP trust handling (not actionable — and not needed — until #1 resolves)

**D — Documentation/git-hygiene only**
- #3 Correct the record that Playwright itself isn't environment-blocked (optional)
- #6 Create a retroactive `tasks/R2-document-management.md`
- #7 Leave commit messages as-is (explicitly recommended, not "fix")
- #8 Confirm `confirm_upload` fix is fully reflected (it already is, in `tasks/R3-document-processing.md`)
- #12 `ai_requests` cardinality note (no action)
- #13 `.mypy_cache` gitignore nicety (optional)

---

## The Three Environment Gaps — Precisely

| Gap | What's actually required to verify it | Can Claude Code do it in this environment right now? |
|---|---|---|
| **Playwright E2E** | Nothing further for *running* Playwright — already proven possible and done. For the *real golden-path content* (item #4), only implementation time and your go-ahead — Postgres/Redis/a startable backend are all already present in this environment. | **Yes**, for both the "can it run" question (already answered) and the golden-path rewrite (would need your explicit approval to start, since this is real test-code implementation, not verification). |
| **Deployed-environment smoke test** | A real deployed environment — which requires OQ-13 resolved, an account provisioned, secrets configured, and an actual deploy having happened. | **No.** Not a tooling gap — there is simply nothing deployed to test against. This is strictly gated behind your decision on item #1. |
| **Standalone Linux `rq worker`** | A working Docker daemon (this host's is unresponsive) or a Linux CI runner actually executing the job. | **No, not in this specific session as configured.** Could be done via (a) you fixing/restarting Docker Desktop locally, or (b) me adding a new CI job on `ubuntu-latest` (a real, if small, implementation task requiring your go-ahead — not something to do silently in a planning pass). |

---

## R12 Closure vs. Production Launch — the distinction that matters here

**R12 (Production Deployment Readiness) can be considered closed as a code/config task.** Every deliverable the remediation plan actually assigned to R12 — CORS, security headers, structured logging, request correlation, the Production Launch Runbook, the scripted smoke test, the basic load test — is built, tested, and committed. None of R12's own deliverables required a platform to be chosen.

**Production launch (`roadmap.md` Phase 19) cannot happen without OQ-13.** Phase 19's own Definition of Done ("all P0 requirements verified against the live production environment") is categorically impossible without a live production environment, which categorically requires a platform decision. This is not R12 being incomplete — it's Phase 19 being a distinct, later phase that has a hard dependency R12 correctly stopped short of resolving unilaterally.

**I am not choosing a platform.** Per your explicit instruction, item #1 stays open until you decide.

---

## Release Status

## **READY WITH CONDITIONS**

Unchanged in kind from the prior audit, but the record is now more precise: one item that looked open (Playwright environment support) is actually resolved; one item that wasn't previously surfaced this precisely (the E2E suite's real-content gap) now is; the confirm_upload fix is confirmed committed and reflected in documentation.

### Exact remaining blockers (production launch, not R12 code-readiness)
1. OQ-13 — container platform decision (yours to make)
2. Deployed-environment smoke test — mechanically blocked behind #1

### Exact non-blocking follow-ups
- Playwright E2E golden-path content rewrite (B — recommended, not required)
- Standalone Linux `rq worker` verification (B — recommended, not required; strong inspection-based confidence already)
- Retry-count semantics decision (C)
- CSV tolerance number decision (C)
- Proxy/IP trust handling (C — becomes relevant only once #1 resolves)
- R2 task file, commit-message note, `ai_requests` cardinality note, `.mypy_cache` gitignore entry (D — pure hygiene, no functional risk either way)

### Recommended execution order
1. **You decide OQ-13** (nothing else in the "must complete" category can proceed without this).
2. Once decided: I write the platform config + wire the CI secret name (small, mechanical).
3. Provision the real platform account/secrets (yours) → first real deploy.
4. Run the adapted `smoke_test.py` against the real deployed origin (closes item #2).
5. In parallel, at your discretion (doesn't block 1–4): approve the Playwright golden-path rewrite (#4) and/or the Linux `rq worker` CI job (#5) — both are real implementation tasks I can start independently of OQ-13.
6. Whenever convenient, the D-category hygiene items (R2 task file, `.mypy_cache` line) — zero risk, zero urgency.

### The next single task to give Claude Code

**Tell me which container platform you're choosing for OQ-13** (Fly.io, Railway, or ECS/Fargate), and whether you'd like me to start the Playwright golden-path rewrite (#4) and/or the Linux `rq worker` CI-job addition (#5) in the meantime — those two don't need OQ-13 resolved first and can proceed in parallel with your platform decision.

Everything that could be verified locally in this pass has been verified. I'm stopping here, as instructed — no implementation started.

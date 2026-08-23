# Task 16: Testing — Coverage Gap Audit & Closure (Frontend)

## Task ID
P16-001

## Feature
Frontend Test Coverage Audit — Component/E2E Gap Closure Against `testing.md` §2 and the P0/P1 Traceability Set

## Objective
Deliver the frontend scope of Phase 16 per the approved frontend implementation plan: "Close E2E gaps to full golden-path coverage; component/a11y coverage audit against §18's traceability table [of the frontend plan]." This is a **verification-and-gap-closure pass**, not a new-feature build — audit test coverage for everything built in Phases 1–15 against `specs/testing.md`'s obligations, close genuine gaps found, and document honestly where a gap cannot be closed (the true golden-path E2E, which requires a real backend that doesn't exist yet for most domains).

## Specification References
- `testing.md` §1.2 — "a P0 or P1 requirement is not 'done' until at least one automated test asserts each of its acceptance criteria" — the standard this audit measured against.
- `testing.md` §2.2 — component test scope/approach (query by role/label/text).
- `testing.md` §2.4 — **amended during this task** (see Implementation Notes) — E2E scope, including the named "cross-tenant denial surfaced correctly in the UI" secondary flow.
- `requirements.md` — the full P0/P1 `FR-*` list, cross-referenced against existing test coverage.

## Requirements
No new `FR-*`/`NFR-*` — this task verifies test coverage for the existing requirement set, per `roadmap.md` Phase 16's framing ("Verification layer for all P0/P1 requirements — no new product requirements introduced").

## Dependencies
- Phases 2–15 (everything this task audits).

## Files Affected
- `specs/testing.md` — modified — §2.4 amended with an honest note on the current frontend-track interim state (see Implementation Notes).
- `components/domain/chat/chat-thread.test.tsx` — new.
- `components/domain/chat/conversation-list.test.tsx` — new.
- `components/domain/chat/document-scope-picker.test.tsx` — new.
- `components/domain/documents/documents-toolbar.test.tsx` — new.
- `components/domain/extractions/template-gallery.test.tsx` — new.
- `e2e/cross-tenant-denial.spec.ts` — new.

## Implementation Notes

### Audit method
Cross-referenced every P0/P1 `FR-*` in `requirements.md` against actual test coverage (Vitest/RTL component tests, Playwright E2E specs), then listed every file under `components/domain/` with no corresponding `.test.tsx` and assessed each for genuine risk (real conditional/state logic vs. simple presentational wrapper). Two specific risk hypotheses were checked directly and found **already covered, not gaps**:
- `FR-AUTH-005` (session refresh) — `lib/api/client.test.ts` already has three dedicated tests for `fetchWithRefresh`'s refresh-and-retry behavior.
- `FR-AI-004` (graceful "I don't know") — `message-bubble.test.tsx` already has a dedicated test for the zero-citation declined-answer variant's distinct styling.

### Real gaps found and closed
Five components had real, untested conditional/state-machine logic tied to P0/P1 requirements:
- **`chat-thread.tsx`** (`FR-AI-001`/`003`/`004`, P0) — the most complex untested component in the app: loading, 404-vs-generic error, empty-thread, populated-messages, and new-vs-existing-conversation scope-picker states, all previously unverified by any test.
- **`conversation-list.tsx`** (`FR-AI-003`, P0) — loading/error/empty/populated states plus the delete-conversation mutation's success/failure toast paths.
- **`document-scope-picker.tsx`** (`FR-AI-002`, P1) — label computation (workspace/single/multi) and selection-toggle logic.
- **`documents-toolbar.tsx`** (`FR-DOC-002`, P0) — search input, view-toggle, and upload-trigger interactions (Select-based filters intentionally left unopened in this pass — no existing test in the codebase opens a Base UI `Select` popover yet, an unknown-jsdom-requirement risk on par with `Command`/`cmdk` before Phase 12 established its polyfill; the toolbar's other, lower-risk interactions were prioritized instead).
- **`template-gallery.tsx`** (`FR-EXT-002`, P1) — loading/error states and template/custom-schema selection.

Two new jsdom gaps surfaced while writing these (same class as `cmdk`'s `ResizeObserver` requirement found in Phase 12): `Element.prototype.scrollTo` (used by `ChatThread` to keep the thread pinned to the latest message) and `Toaster`'s `window.matchMedia` dependency — both stubbed locally in the affected test files, not globally in `vitest.setup.ts`, consistent with the existing scoping convention.

**Deliberately not closed this pass** (lower risk, or already indirectly exercised): `delete-dialog.tsx`, `rename-dialog.tsx`, `tag-editor-dialog.tsx`, `document-row-actions.tsx`, `summary-row.tsx`, `citation-chip.tsx`, `usage-strip.tsx`, and a handful of simple presentational components (`auth-card.tsx`, `form-error-banner.tsx`, `google-button.tsx`, `empty-thread-prompt.tsx`, `streaming-indicator.tsx`, `document-card.tsx`, `file-type-icon.tsx`). Listed explicitly as a remaining, non-blocking gap below rather than silently left uncounted.

### E2E gap closed: cross-tenant denial, proven through a real browser
`testing.md` §2.4 explicitly names "a cross-tenant denial surfaced correctly in the UI" as a required secondary E2E flow — distinct from, and not satisfied by, the many "unreachable backend" connectivity-error E2E tests already in the suite (a live 502 from the real backend-less BFF can never actually produce the 404 this flow is about). This flow WAS already correctly proven at the component level (MSW-mocked 404s in `chat-thread.test.tsx`, `extraction-results-view.test.tsx`, `comparison-report-view.test.tsx`, `document-viewer.test.tsx`), but no committed Playwright spec exercised it through an actual browser rendering the real page. Added `e2e/cross-tenant-denial.spec.ts`, using `page.route()` to mock a 404 at the BFF-proxy layer for each of the four resource-detail routes (documents, chat, extractions, comparisons), asserting the real browser renders the exact non-leaking "doesn't exist, or you don't have access to it" copy with no retry action — closing the one specifically-named E2E gap this phase's own scope calls out.

### Spec amendment: the golden-path E2E gap is real and is documented, not silently left unresolved
The true golden-path E2E (`register → verify → upload → ready → chat → extract → compare → search`, `testing.md` §2.4) structurally cannot run today — it requires a real backend that doesn't exist yet for most domains (only Phases 3/6/7/8's backend-only work is live; every other domain's BFF call still genuinely 502s). This has been true and handled consistently, phase by phase, since Phase 9 (every E2E spec file already carries a comment explaining it), but `testing.md` itself never stated this interim reality explicitly. Per `CLAUDE.md`'s SDD discipline ("never silently change requirements... resolve explicitly"), added one paragraph to §2.4 acknowledging the substitution (connectivity-error-path + mocked cross-tenant-denial coverage stands in for the golden path until a backend exists) without weakening or replacing the golden-path requirement itself — it remains the target, explicitly deferred, not redefined.

### A11y spot-check
Reviewed the newly-tested components plus a handful of interactive dialogs/pickers for missing accessible names or keyboard-trap issues. No new gaps found — every interactive element already carries an accessible name or label (verified structurally, since every new test in this task queries by role/label per `testing.md` §2.2, which incidentally proves the accessible name/role exists), consistent with the accessibility discipline already established across Phases 1–15.

## Tests
- `components/domain/chat/chat-thread.test.tsx` (5 tests) — 404-vs-generic error distinction, empty-thread prompt, populated messages with citations, scope-picker visibility rule.
- `components/domain/chat/conversation-list.test.tsx` (5 tests) — connectivity error with retry, empty state, populated list with active-item highlighting and scope labels, delete success/failure toasts.
- `components/domain/chat/document-scope-picker.test.tsx` (5 tests) — workspace/single/multi label computation, selection toggle, disabled-while-streaming.
- `components/domain/documents/documents-toolbar.test.tsx` (4 tests) — search input, view-toggle pressed state and switching, upload trigger.
- `components/domain/extractions/template-gallery.test.tsx` (3 tests) — connectivity error with retry, template rendering and selection, custom-schema selection.
- `e2e/cross-tenant-denial.spec.ts` (4 tests) — the "404, not 403" pattern proven through a real browser for documents, chat conversations, extractions, and comparisons.

## Acceptance Criteria
- Every P0/P1 requirement with frontend-observable behavior has at least one automated test, or the specific gap (true golden-path E2E) is explicitly documented as blocked on backend availability rather than silently unaddressed.
- The `testing.md` §2.4-named cross-tenant-denial E2E flow is proven through a real browser, not only at the component level.
- No regressions in Phases 1–15's existing test suite.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (182/182 Vitest, up from 160; 59/59 Playwright, up from 55)
- [x] No requirement silently changed or reinterpreted — the golden-path E2E gap is documented explicitly (with rationale) rather than papered over with a substitute that pretends to be the same thing
- [x] `specs/testing.md` updated — the one spec change this task required
- [x] Browser QA performed — confirmatory spot-check only (no production code changed this task, only test files/specs/docs); no console errors on `/chat`, `/extractions`
- [x] Regression check performed across Phases 1–15 — no regressions found; 182/182 Vitest, 59/59 Playwright, `tsc --noEmit` clean, `eslint` clean, `next build` clean, 87/87 backend pytest, Docker Compose healthy
- [x] Basic performance review performed — no production code changed, so no bundle-size/re-render impact; test files never ship
- [x] Security review performed — no new client-side secrets, no new unsafe-HTML rendering, no new API surface; the new E2E spec only verifies existing security behavior (404-not-403), it doesn't add any
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

## Known Limitations / Follow-Up (not fixed this task, scope-appropriately deferred)
- **The true golden-path E2E suite remains unbuilt**, structurally blocked on backend availability for most domains — `testing.md` §2.4 now documents this explicitly (see Implementation Notes) rather than leaving it an implicit, undocumented gap.
- **A handful of lower-risk domain components remain without a dedicated test file**: `delete-dialog.tsx`, `rename-dialog.tsx`, `tag-editor-dialog.tsx`, `document-row-actions.tsx`, `summary-row.tsx`, `citation-chip.tsx`, `usage-strip.tsx`, and several simple presentational components. None currently has known conditional-logic risk; flagged here for future coverage rather than silently omitted.
- **`documents-toolbar.tsx`'s Select-based filters (status/tag/sort) remain untested** — no test in the codebase yet opens a Base UI `Select` popover, an unexplored jsdom-polyfill risk deferred rather than rushed.
- **Settings (`/settings`) and Admin user/system pages (`/admin/users`, `/admin/system`) remain `PhasePlaceholder`** — a pre-existing, already-documented gap (not discovered by this task) with no dedicated roadmap phase; out of scope for a testing-audit phase to build.

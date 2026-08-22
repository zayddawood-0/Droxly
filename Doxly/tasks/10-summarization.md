# Task 10: Summarization (Frontend)

## Task ID
P10-001

## Feature
Summarization — Entry Points, Type Selector, Polling Result View

## Objective
Deliver the frontend for `FR-SUM-001`/`FR-SUM-002` per the approved frontend implementation plan's Phase 10 entry: a summary entry point reachable from both the Document Viewer and the Documents list, a summary-type selector, and a polling-based result view — no dedicated route, matching the plan's own framing ("a summary entry point from Viewer/Documents ... polling result view"). Built against `api.md`'s documented `/summaries` contract and tested against the real (currently backend-less) BFF proxy, consistent with every prior frontend phase.

## Specification References
- `requirements.md` §1.7 (`FR-SUM-001`, `FR-SUM-002`) — the requirement set this task targets.
- `ui-ux.md` §9 (Summarization) — **added during this task** (see Implementation Notes); this task's primary UI contract.
- `api.md` §5 (`/summaries`) — create (202, async), list (paginated, never overwritten), and detail (polled) endpoints.
- `database.md` §6 — `document_summaries` schema (already built in Phase 3 with the correct `status` enum, confirmed unchanged).

## Requirements
- `FR-SUM-001` (P0): Generate a summary at a chosen type (brief/detailed/bullet_points) for a `ready` document; async, quality-checked server-side, persisted for reuse.
- `FR-SUM-002` (P1): Regenerating never overwrites a prior summary — the past-summaries list always stays accessible, newest first.

## Dependencies
- Phase 4 (Document Management) — Document Viewer's action rail and the Documents list row-actions menu, both extended with a "Summarize" entry point rather than duplicated.
- Phase 8 (LangGraph) — the backend Summarization graph this UI is built to consume once a backend router exists; not itself built in this task.

## Files Affected
- `specs/ui-ux.md` — modified — added the missing §9 Summarization section (see Implementation Notes), renumbered §9–§15 to §10–§16 accordingly.
- `lib/api/summaries.ts` — new — typed functions for every `/summaries` endpoint in `api.md`.
- `hooks/use-summaries.ts` — new — `useSummariesQuery`, `useSummaryQuery` (polling), `useCreateSummaryMutation`.
- `components/domain/summaries/summary-row.tsx`, `components/domain/summaries/summary-dialog.tsx` — new.
- `app/(dashboard)/documents/[documentId]/document-viewer.tsx` — modified — "Summarize" action button now opens `SummaryDialog` instead of a `comingSoon` tooltip.
- `components/domain/documents/document-row-actions.tsx` — modified — added a "Summarize" menu item.
- Tests: `components/domain/summaries/summary-dialog.test.tsx`.

## Implementation Notes
- **Spec gap resolved:** `ui-ux.md` had no Summarization section at all — the page list jumped from AI Chat (§8) straight to Extractions (§9), even though `FR-SUM-*` clearly needed a documented UI shape. Added a full §9 entry (Purpose/Layout/Components/Interactions/all four states/Responsive/Accessibility, matching every other section's structure exactly) before implementing against it, per `CLAUDE.md`'s SDD rules — not improvised from the requirement text alone. Confirmed no other spec file cross-references the renumbered section indices before renumbering.
- **A second, smaller spec inaccuracy caught during browser QA and fixed in the same pass:** the newly-added §9 originally claimed the dialog "becomes a full-height sheet on mobile," an assumption that turned out to be false — no dialog in this codebase converts to a sheet at mobile width (`components/ui/dialog.tsx` is always a responsive centered modal). Corrected the spec text to describe what's actually built, rather than leaving an inaccurate claim in place.
- **No standalone route** — per the frontend plan's own framing and the confirmed absence of "Summarization" from `ui-ux.md` §0's sidebar nav list, this is a `Dialog` launched from two existing surfaces, not a new page.
- **Per-row query gating:** `document-row-actions.tsx` renders once per row in a documents list; `SummaryDialog`'s `useSummariesQuery` is gated with `enabled: open` so closed dialogs (the common case, N-1 rows at any time) never fire an eager fetch — found and fixed during implementation, before it could become an N-simultaneous-request bug once real data exists.
- **Polling, not SSE** — `useSummaryQuery`'s `refetchInterval` re-fetches every 2s while `status === "processing"` and stops on any terminal status, matching `api.md`'s explicit "client polls" framing (summarization is a queued background job, unlike chat's inline SSE stream).
- Bullet-point summaries render as a real `<ul>`/`<li>` list (stripping any literal `-`/`•` prefix from the raw content), not literal dash characters in a paragraph.

## Tests
- `components/domain/summaries/summary-dialog.test.tsx` — empty state shows the generate form directly; past summaries list newest-first with expand-to-view; bullet_points renders as a real list; failed summary shows Retry and re-submits; **the actual polling loop transitions processing → completed** (a stateful MSW handler proving the interval-based re-fetch genuinely works, not just a single-shot fetch); list-fetch failure shows a retry affordance.
- E2E: no new dedicated spec — the interactive flow requires document data the real backend-less BFF can't provide (same limitation documented in Phases 4/5/9's reports); `e2e/route-smoke.spec.ts`'s existing no-console-errors check on `/documents/doc_test-id` already covers that mounting the new dialog/hooks doesn't throw. Interactive states are proven at the component level (this task's test file) and via mocked-network Playwright screenshots during browser QA, per the established pattern.

## Acceptance Criteria
(Adapted from `requirements.md` §1.7, frontend-observable subset)
- Given a `ready` document, when the user picks a summary type and clicks Generate from either the Document Viewer or the Documents list, then a new processing entry appears immediately.
- Given a processing summary, when it completes, then its content replaces the processing indicator without the user needing to manually refresh (polling).
- Given a document with prior summaries, when the user generates a new one, then all prior summaries remain listed and accessible.
- Given a failed summary, when the user clicks Retry, then a fresh request is submitted (never silently mutating the failed row).
- Given no reachable backend, list/generate failures show the shared connectivity-error handling, never a blank dialog or an unhandled rejection.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (100/100 Vitest, 43/43 Playwright)
- [x] No requirement silently changed or reinterpreted — the missing ui-ux.md section was added explicitly, not assumed
- [x] `specs/ui-ux.md` updated (new §9, renumbered §10–§16, one inaccurate claim corrected after QA) — the spec changes this task required
- [x] Browser QA performed at desktop/mobile via mocked-network screenshots (real-BFF interactive states aren't reachable, consistent with prior phases); found and corrected the dialog's mobile-sheet spec claim
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

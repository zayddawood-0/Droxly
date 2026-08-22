# Task 12: Document Comparison (Frontend)

## Task ID
P12-001

## Feature
Document Comparison — A/B Document Picker, Past Comparisons History, Side-by-Side/Unified Diff Report with Change-Type Filtering and Degraded-Alignment Path

## Objective
Deliver the frontend for `FR-COMP-001`–`FR-COMP-003` per the approved frontend implementation plan's Phase 12 entry: an A/B document picker reachable from the sidebar and the Document Viewer's "Compare" action, a persisted comparison-history list, and a report view rendering additions/deletions/modifications as a genuine side-by-side diff on desktop (collapsing to a unified stacked diff on mobile), with change-type filtering, per-change citation deep-links, and an explicit degraded-alignment path for structurally dissimilar documents. Built against `api.md`'s `/comparisons` contract and tested against the real (currently backend-less) BFF proxy, consistent with every prior frontend phase.

## Specification References
- `requirements.md` §1.9 (`FR-COMP-001`–`FR-COMP-003`) — the requirement set this task targets.
- `ui-ux.md` §11 (Comparison) — **amended during this task** (see Implementation Notes); this task's UI contract.
- `api.md` §7 (`/comparisons`) — create (202, async), detail (polled, structured result), list (history) — **the result shape was amended during this task** (see Implementation Notes).
- `database.md` §3.12 — `comparisons` schema (built in Phase 3; `CHECK (document_a_id <> document_b_id)` mirrored client-side by `DocumentPicker`'s new `excludeId` prop).
- `langgraph.md` §5 (Comparison graph) — the alignment/classification categories (factual/numeric/wording) this UI's `ChangeTypeBadge` renders, and the degraded-report routing this UI's low-`alignment_quality` path handles.

## Requirements
- `FR-COMP-001` (P0): Select two `ready` documents and request a comparison; result is a structured, semantically-aligned report classified by change type.
- `FR-COMP-002` (P0): The report renders with side-by-side/unified diff highlighting and persists for later viewing (history list).
- `FR-COMP-003` (P2): Comparison degrades gracefully — an explicit message, not a forced diff — when the two documents are too structurally different to align.

## Dependencies
- Phase 4 (Document Management) — Document Viewer's action rail, extended so "Compare" deep-links in with `?document_a=` pre-filled.
- Phase 8 (LangGraph) — the backend Comparison graph this UI is built to consume once a backend router exists; not itself built in this task.
- Phase 11 (Extraction) — reuses `DocumentPicker` (extended with an `excludeId` prop here) and the citation-deep-link/polling-result-view patterns established there, rather than reimplementing them.

## Files Affected
- `specs/ui-ux.md` — modified — §11 Comparison: added the "past comparisons" history list to the documented layout/empty state (see Implementation Notes).
- `specs/api.md` — modified — §7 `GET /comparisons/{id}`: spelled out the previously-elided `result` shape (`ComparisonResult`/`ComparisonSegment`/`ComparisonModification`) (see Implementation Notes).
- `lib/api/comparisons.ts` — new — typed functions/types for every `/comparisons` endpoint.
- `hooks/use-comparisons.ts` — new — `useComparisonsQuery` (history), `useComparisonQuery` (polling), `useCreateComparisonMutation`.
- `components/domain/documents/document-picker.tsx` — modified — added an optional `excludeId` prop so the paired A/B pickers can't select the same document.
- `components/domain/comparisons/change-type-badge.tsx`, `change-summary-strip.tsx`, `diff-view.tsx` — new.
- `app/(dashboard)/compare/compare-view.tsx` — new — A/B pickers + past-comparisons list + "Compare".
- `app/(dashboard)/compare/page.tsx` — modified — wired `CompareView` (was `PhasePlaceholder`).
- `app/(dashboard)/compare/[comparisonId]/comparison-report-view.tsx` — new — pending/processing/completed(normal + degraded)/failed/not-found states, polling, change-type filtering, retry.
- `app/(dashboard)/compare/[comparisonId]/page.tsx` — modified — wired `ComparisonReportView` (was `PhasePlaceholder`).
- `app/(dashboard)/documents/[documentId]/document-viewer.tsx` — modified — "Compare" action now links to `/compare?document_a={id}` instead of an unparameterized route.
- Tests: `components/domain/comparisons/{change-type-badge,change-summary-strip,diff-view}.test.tsx`, `components/domain/documents/document-picker.test.tsx`, `app/(dashboard)/compare/[comparisonId]/comparison-report-view.test.tsx`.
- `e2e/compare.spec.ts` — new.

## Implementation Notes
- **Spec gap resolved (ui-ux.md):** `GET /comparisons` exists specifically to serve history (`api.md` explicitly marks it "Fulfills: FR-COMP-002 (history)", and `database.md`'s `(user_id, created_at DESC)` index exists for exactly this), but §11's documented layout never placed it on the page. Added a "past comparisons" list to the Layout/Empty-state bullets, mirroring Extractions' §10 pattern, before implementing against it.
- **Spec gap resolved (api.md):** `GET /comparisons/{id}`'s `result` field was previously `{ additions: [...], deletions: [...], modifications: [...] }` with the array element shapes elided. Resolved explicitly by defining `ComparisonSegment` (`{ document: "a"|"b", page_number, excerpt }`, for pure additions/deletions from `langgraph.md`'s "unmatched segments" case) and `ComparisonModification` (`{ change_type, a_page_number, a_excerpt, b_page_number, b_excerpt, explanation }`, for aligned-pair changes) — reusing the app's one existing citation shape (`page_number`/`snippet` from `database.md`'s `citations` table) rather than inventing a new one. `change_type` is constrained to `"factual"|"numeric"|"wording"`, matching `ui-ux.md`'s `ChangeTypeBadge` enumeration exactly (langgraph.md's own list is `e.g.`-qualified and non-exhaustive; the UI spec's concrete three-value list was treated as authoritative for the type).
- **`DocumentPicker` reuse, not duplication:** extended (not forked) with an `excludeId` prop so Document B's picker hides whatever Document A already selected — a client-side mirror of the API's `422 identical_documents` guard — rather than building a second single-select combobox.
- **Citation reuse:** each change's excerpt renders through the existing `CitationChip` (built in Phase 9 for chat), constructing a `MessageCitation`-shaped object (`{document_id, page_number, snippet, relevance_score: null}`) from the comparison segment — no new citation component, no new deep-link mechanism.
- **Genuine side-by-side, not a cosmetic split:** the desktop `DiffView` uses a two-column CSS grid (`grid-cols-subgrid` per row) where additions show real content only in the Document B column (Document A column renders an honest "No corresponding content" placeholder) and deletions the mirror image — never a fabricated aligned pair. Mobile collapses the same normalized change list into stacked cards labeled by document, per `ui-ux.md`'s responsive requirement.
- **"Next change" navigation:** `ui-ux.md` §11's accessibility bullet ("diff regions are navigable via a 'next change' keyboard shortcut") is satisfied with a "Change X of N" counter plus Prev/Next buttons that scroll the target change into view and move focus to it — a lightweight implementation matched to the requirement's own scope, not a full virtualized diff engine.
- **Retry, not just "back":** the failed-comparison state resubmits the same `document_a_id`/`document_b_id` via `useCreateComparisonMutation` and navigates to the new comparison's report, mirroring Extraction's `handleRetry` — `ui-ux.md`'s "Error state: Comparison job failure shows a retry action" is a genuine retry, not a dead-end link.
- **Query-level error copy kept consistent with Extraction:** the fatal-load error state always shows "We couldn't load this comparison right now." (except for a distinct 404 message) regardless of whether the underlying failure was a connectivity error — matching `extraction-results-view.tsx`'s established behavior exactly, rather than introducing a new, inconsistent connectivity-specific branch at the page level (mutation-level toasts still classify connectivity errors, as elsewhere).
- **jsdom gaps surfaced by testing `DocumentPicker`'s popover directly for the first time:** `cmdk`'s `Command` list uses `ResizeObserver` and `scrollIntoView`, neither implemented by jsdom — stubbed locally in `document-picker.test.tsx` (not globally in `vitest.setup.ts`, to keep the stub scoped to the one test file that actually exercises the popover interaction).

## Tests
- `components/domain/comparisons/change-type-badge.test.tsx` — all six kinds render a distinct text label (never color alone).
- `components/domain/comparisons/change-summary-strip.test.tsx` — counts per category; filter toggle on/off.
- `components/domain/comparisons/diff-view.test.tsx` — every addition/deletion/modification excerpt renders; filtering narrows to the selected type; distinct empty states for "no differences at all" vs. "filter matches nothing."
- `components/domain/documents/document-picker.test.tsx` — `excludeId` hides the paired document from the popover list.
- `app/(dashboard)/compare/[comparisonId]/comparison-report-view.test.tsx` — **the actual polling loop transitions processing → completed** (stateful MSW handler); the degraded-alignment path renders the explanatory message and both "View document" fallbacks instead of a forced diff; a failed comparison shows Retry; a 404 shows a distinct not-found message.
- E2E (`e2e/compare.spec.ts`, 2 tests): the compare page shows real connectivity errors for both the document picker and the history list, not blank sections; an unreachable comparison report shows the connectivity error, not a blank page. Both exercise the real backend-less BFF, per the established no-mocks pattern for E2E.

## Acceptance Criteria
(Adapted from `requirements.md` §1.9, frontend-observable subset)
- Given two different `ready` documents, when the user selects both and clicks Compare, then a new processing comparison is created and its report view opens.
- Given a processing comparison, when it completes, then the diff report replaces the processing indicator without a manual refresh (polling).
- Given a completed high/medium-alignment comparison, then additions/deletions/modifications render as a side-by-side diff on desktop and a unified stacked diff on mobile, each change carrying a text-labeled type badge and a citation into the source document.
- Given a low-alignment comparison, then the report view shows an explanatory message and a way to view both documents individually, never a misleading forced diff.
- Given a user selects a change-type filter, then only changes of that type remain visible; selecting it again clears the filter.
- Given a failed comparison, when the user clicks Retry, then a fresh comparison is submitted with the same two documents.
- Given no reachable backend, list/create/detail failures show the shared connectivity-error handling, never a blank view or an unhandled rejection.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (134/134 Vitest, 49/49 Playwright)
- [x] No requirement silently changed or reinterpreted — the two spec gaps (ui-ux.md's missing history list, api.md's elided result shape) were resolved explicitly in the spec before implementation, not assumed
- [x] `specs/ui-ux.md` and `specs/api.md` updated — the spec changes this task required, both documented above with rationale
- [x] Browser QA performed at desktop/mobile via mocked-network screenshots (real-BFF interactive states aren't reachable, consistent with prior phases); side-by-side diff, degraded-alignment path, and unified mobile diff all verified rendering correctly with no console errors
- [x] Regression check performed across Phases 1–11 (navigation, auth, documents, chat, summarization, extraction, forms, API interactions, shared components, responsive layouts) — no regressions found; backend pytest 87/87, Docker Compose healthy
- [x] Basic performance review performed — no meaningful issues found (query deduplication across `DocumentPicker` instances confirmed via shared TanStack Query key, `DiffView` normalization memoized, polling matches the established 2s interval pattern)
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

# Task 11: Structured Extraction (Frontend)

## Task ID
P11-001

## Feature
Structured Extraction — Document Picker, Template Gallery, Custom Schema Builder, Polling Result View with Inline Correction

## Objective
Deliver the frontend for `FR-EXT-001`–`FR-EXT-004` per the approved frontend implementation plan's Phase 11 entry: a document-scoped extraction workflow reachable from the sidebar and the Document Viewer's "Extract" action, letting a user run a preset template or a custom field schema against a `ready` document, view a polling-based result grid with per-field confidence and citation, and correct not-found or wrong values inline. Built against `api.md`'s documented `/extractions` contract and tested against the real (currently backend-less) BFF proxy, consistent with every prior frontend phase.

## Specification References
- `requirements.md` §1.8 (`FR-EXT-001`–`FR-EXT-004`) — the requirement set this task targets.
- `ui-ux.md` §10 (Extraction, post Phase-10 renumbering) — this task's UI contract; no gap found (unlike Phases 9/10, no spec edit was required here).
- `api.md` §6 (`/extractions`) — templates (list), create (202, async, template or custom schema), list-for-document, detail (polled), correction (`PATCH`).
- `database.md` — `extractions` schema (built in Phase 3, confirmed unchanged).

## Requirements
- `FR-EXT-001` (P0): Define or select a field schema and run extraction; result is structured, schema-validated, with per-field confidence and citation.
- `FR-EXT-002` (P1): Preset templates (invoice, contract, resume, research paper) offered alongside custom schema definition.
- `FR-EXT-003` (P1): Fields the model can't find are returned `null` with a `not_found_reason`, shown distinctly — never a fabricated placeholder.
- `FR-EXT-004` (P2): Manual correction of an extracted value persists with the extraction record.

## Dependencies
- Phase 4 (Document Management) — Document Viewer's action rail, extended so "Extract" deep-links into this flow with `?document=` pre-filled rather than duplicating document selection.
- Phase 8 (LangGraph) — the backend Extraction graph this UI is built to consume once a backend router exists; not itself built in this task.
- Phase 7 (Retrieval/Citations) — the citation shape (`page_number`/`snippet`) this UI renders per field, reusing the same citation data model as Chat/Summarization rather than inventing a new one.

## Files Affected
- `lib/api/extractions.ts` — new — typed functions/types for every `/extractions` endpoint in `api.md`.
- `hooks/use-extractions.ts` — new — `useExtractionTemplatesQuery`, `useDocumentExtractionsQuery`, `useExtractionQuery` (polling), `useCreateExtractionMutation`, `useCorrectExtractionMutation`.
- `hooks/use-editable-field.ts` — new — shared Enter-to-save/Escape-to-cancel inline-edit state machine, reused across the desktop table row and mobile card.
- `components/domain/documents/document-picker.tsx` — new — single-select document combobox; deliberately kept separate from Chat's `DocumentScopePicker` (multi-select) since the selection semantics genuinely differ.
- `components/domain/extractions/confidence-badge.tsx`, `template-gallery.tsx`, `schema-builder.tsx`, `extraction-field-row.tsx`, `extraction-field-card.tsx` — new.
- `app/(dashboard)/extractions/extractions-view.tsx` — new — document picker + past-extractions list + new-extraction (template gallery / custom schema builder) form.
- `app/(dashboard)/extractions/page.tsx` — modified — wired `ExtractionsView` in a `<Suspense>` boundary (reads `?document=` via `useSearchParams`).
- `app/(dashboard)/extractions/[extractionId]/extraction-results-view.tsx` — new — pending/processing/completed/failed/not-found states, polling, inline correction, retry.
- `app/(dashboard)/extractions/[extractionId]/page.tsx` — modified — wired `ExtractionResultsView`.
- `app/(dashboard)/documents/[documentId]/document-viewer.tsx` — modified — "Extract" action now links to `/extractions?document={id}` instead of an unparameterized route.
- Tests: `components/domain/extractions/schema-builder.test.tsx`, `confidence-badge.test.tsx`, `extraction-field-row.test.tsx`, `app/(dashboard)/extractions/[extractionId]/extraction-results-view.test.tsx`.
- `e2e/extractions.spec.ts` — new.

## Implementation Notes
- **No spec gap found** — unlike Phases 9 and 10, `api.md`'s `/extractions` contract (including the `PATCH` correction endpoint) and `ui-ux.md`'s Extraction section were already complete and consistent; implemented directly against them with no spec edits required.
- **Document picker reuse decision:** `DocumentPicker` (single-select) is new infrastructure shared with the upcoming Comparison phase (`ui-ux.md` §11 also names it), not a Phase-11-only component — built as shared `components/domain/documents/` rather than nested under `extractions/`. Deliberately kept distinct from Chat's `DocumentScopePicker` (multi-select) rather than unifying them, since single- vs multi-select are genuinely different selection semantics, not a DRY opportunity.
- **Polling, not SSE** — `useExtractionQuery`'s `refetchInterval` follows the exact same pattern established in Phase 10's `useSummaryQuery`: re-fetch every 2s while `status === "processing"`, stop on any terminal status.
- **Shared inline-edit hook:** `useEditableField` factors out the Enter/Escape edit-state machine so the desktop table row (`extraction-field-row.tsx`) and mobile card (`extraction-field-card.tsx`) — two different renderings of the same field data — don't duplicate the interaction logic.
- **Not-found and corrected styling:** not-found fields render `italic text-muted-foreground` with their `not_found_reason`, never blank or a fabricated value, per `FR-EXT-003`; corrected fields render `text-primary` to visibly distinguish a human-entered value from a model-extracted one.
- **Two issues found and fixed during browser QA** (mocked-network Playwright screenshots, real-BFF interactive states unreachable as in prior phases):
  1. **Layout overlap** — `extractions-view.tsx`'s header row rendered `<DocumentPicker>` as an unconstrained flex child next to a label block with only `min-w-0` (no `flex-1`), so the picker's internal `w-full` Button crowded out the "Document" label and filename. Fixed by wrapping the picker in `<div className="w-64 shrink-0">` and adding `flex-1` to the label's wrapper.
  2. **Raw slug display** — the past-extractions list showed the raw `template_key` value (e.g. `"invoice"`) instead of a human-readable label. Fixed with a `humanizeTemplateKey()` helper (splits on `_`, title-cases each word, falls back to "Custom schema" for `null`).
  Both fixes verified via a follow-up screenshot before this task was closed out.
- **jsdom dual-render testing gotcha:** `ExtractionResultsView` renders both the desktop table (`hidden md:block`) and mobile cards (`md:hidden`) simultaneously in jsdom (no real CSS media-query filtering in the test environment), so assertions use `getAllByText(...).length > 0` / indexed `findAllByRole(...)[0]` rather than singular `getByText`/`findByRole`, matching the same fix already applied in Phase 9's message-bubble tests.

## Tests
- `components/domain/extractions/schema-builder.test.tsx` — field name edits via controlled-component keystroke, required-checkbox toggle, add-field, remove-field (never below one row).
- `components/domain/extractions/confidence-badge.test.tsx` — high/medium/low bucket thresholds (≥0.8/≥0.5/<0.5) render the correct percentage and color.
- `components/domain/extractions/extraction-field-row.test.tsx` — not-found styling with reason (never blank), citation rendering, Enter-to-save/Escape-to-cancel edit, corrected-value styling.
- `app/(dashboard)/extractions/[extractionId]/extraction-results-view.test.tsx` — **the actual polling loop transitions processing → completed** (stateful MSW handler), not-found field shown distinctly with a working inline correction round-trip, failed extraction shows Retry, a 404 shows a distinct not-found message (not a generic error).
- E2E (`e2e/extractions.spec.ts`, 4 tests): document-picker prompt when no document is pre-selected; document-picker connectivity error (not a blank popover); pre-selected-document history/template connectivity errors (not blank sections); unreachable-extraction-result connectivity error (not a blank page). All exercise the real backend-less BFF, per the established no-mocks pattern for E2E.

## Acceptance Criteria
(Adapted from `requirements.md` §1.8, frontend-observable subset)
- Given a `ready` document, when the user selects a template or defines a custom schema and runs extraction, then a new processing extraction is created and its result view opens.
- Given a processing extraction, when it completes, then the field grid replaces the processing indicator without a manual refresh (polling), showing confidence and citation per field.
- Given a field the model could not find, then it renders distinctly (never blank, never a fabricated value) with its reason.
- Given a user edits a field's value, when they press Enter, then the correction is persisted and shown as visibly corrected; Escape cancels without saving.
- Given a failed extraction, when the user clicks Retry, then a fresh extraction is submitted with the same schema/template.
- Given no reachable backend, list/create/detail failures show the shared connectivity-error handling, never a blank view or an unhandled rejection.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (116/116 Vitest, 47/47 Playwright)
- [x] No requirement silently changed or reinterpreted — no spec gaps found this phase, implemented directly against the existing `api.md`/`ui-ux.md` contract
- [x] No spec changes required — `api.md` §6 and `ui-ux.md` §10 were already complete and accurate
- [x] Browser QA performed at desktop/mobile via mocked-network screenshots (real-BFF interactive states aren't reachable, consistent with prior phases); found and fixed a layout overlap and a raw-slug display issue, both re-verified fixed
- [x] Regression check performed across Phases 1–10 (navigation, auth, documents, chat, summarization, forms, API interactions, shared components, responsive layouts) — no regressions found
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

# Task 05: Document Processing (Frontend — Status UI)

## Task ID
P05-001

## Feature
Document Processing — Live Status UI, Failed State, Reprocess Action

## Objective
Complete `FR-DOC-008` and `FR-PROC-005` on the frontend: wire the Document Viewer to the real `GET /documents/{id}/status/stream` (SSE) and `GET /documents/{id}/status` (polling fallback) endpoints so a document's pipeline stage updates live, without a page reload; replace the static in-progress/failed placeholders built as a stub in Phase 4 with the shared `StatusBadge` vocabulary plus a working "Retry processing" action for `failed` documents. No backend processing pipeline is built in this task — per the approved frontend implementation plan, Phase 5's frontend deliverable is the status UI consuming endpoints `api.md` already documents; the pipeline itself (`FR-PROC-001/002/004`, the RQ worker) is backend track work outside this frontend session.

## Specification References
- `requirements.md` §1.3/§1.4 (`FR-DOC-008`, `FR-PROC-004`, `FR-PROC-005`) — the requirement set this task targets.
- `api.md` — `GET /documents/{id}/status`, `GET /documents/{id}/status/stream` (SSE contract: `event: status`, terminal `ready`/`failed`), `POST /documents/{id}/reprocess` (202, 404, 409 `invalid_status`).
- `ui-ux.md` §7 (Document Viewer) — processing-status view replacing the content pane, failed state's "Retry processing" action; §"Processing Indicators" — the one `StatusBadge` vocabulary, no page-specific status styling.
- `architecture.md` — "Frontend polls or subscribes (SSE) to status" sequence note.

## Requirements
- `FR-DOC-008` (P0): Document Viewer reflects live pipeline stage (`queued → extracting → chunking → embedding → ready`/`failed`) without a full reload. Implemented via SSE with an automatic polling fallback on stream error, per the endpoint's documented contract.
- `FR-PROC-005` (P1): A user can retry processing for a `failed` document via a "Retry processing" action in the content pane.
- `FR-PROC-004` (P0, frontend-observable half only): The failed state renders `processing_error` verbatim (already sanitized server-side per `NFR-SEC-009`) — no frontend sanitization logic needed or added.

## Dependencies
- Phase 4 (Document Management) — `StatusBadge`, `useDocumentQuery`, the Document Viewer shell this task extends in place rather than rebuilding.

## Files Affected
- `lib/api/documents.ts` — modified — added `reprocessDocument(id)`.
- `hooks/use-documents.ts` — modified — added `useReprocessDocumentMutation()`.
- `hooks/use-document-status-stream.ts` — new — SSE-with-polling-fallback hook, writes into the same TanStack Query cache entry `useDocumentQuery` reads.
- `hooks/use-document-status-stream.test.tsx` — new.
- `app/(dashboard)/documents/[documentId]/document-viewer.tsx` — modified — wires the live-status hook; `DocumentContentPane`'s in-progress branch now renders `StatusBadge` + a stage description instead of a static Clock icon; failed branch gained the "Retry processing" button.
- `app/(dashboard)/documents/[documentId]/document-viewer.test.tsx` — new.

## Implementation Notes
- SSE first, polling fallback on `EventSource.onerror` — matches `api.md`'s "the frontend uses SSE where supported and falls back to polling" contract exactly; this is also what happens by default against this track's backend-less BFF (every environment so far), so the fallback path is the one continuously exercised until a real backend lands.
- Status updates land via `queryClient.setQueryData` on the exact key `useDocumentQuery` owns (`["documents","detail",id]`) — one source of truth, not a second piece of state the viewer has to reconcile.
- The hook takes an internal `pollIntervalMs` parameter (default 3000ms, overridable) purely for test speed — production call sites never pass it.
- `useReprocessDocumentMutation` invalidates `["documents"]` broadly (same pattern as the existing update/delete mutations) — the optimistic `setQueryData` write covers the gap until that refetch lands.

## Tests
- Component/unit (Vitest + Testing Library + MSW, a hand-rolled `MockEventSource` stubbed onto `global.EventSource` since jsdom has no native implementation) — `use-document-status-stream.test.tsx`: SSE status event applies to the cache, stream-error triggers polling fallback, no connection opens for an already-terminal status. `document-viewer.test.tsx`: in-progress stage shows the shared badge + description, failed state's "Retry processing" moves the document back to `queued`, a reprocess failure surfaces the connectivity-safe toast.
- E2E: no new dedicated spec — the existing `e2e/route-smoke.spec.ts` console-error check on `/documents/doc_test-id` already covers that mounting the new SSE-consuming code path doesn't throw against the real (backend-less) BFF; the interactive states themselves require document data no real backend yet returns, so they're proven at the component level per `testing.md`'s test-pyramid guidance rather than faked at the E2E level.
- Manual/visual QA: mocked-network Playwright screenshots (`page.route()`, not part of the automated suite) confirmed the extracting/embedding/failed states and the failed state's mobile layout render correctly — see Phase 5 Completion Report.

## Acceptance Criteria
(Adapted from `requirements.md` §1.3/§1.4, frontend-observable subset)
- Given a document mid-pipeline, when the user views it, then the current stage is shown via the shared `StatusBadge` and updates without a full page reload.
- Given the SSE connection fails, when the document is still non-terminal, then polling silently takes over on the same cadence.
- Given a `failed` document, when the user views it, then `processing_error` and a "Retry processing" action are shown in place of content.
- Given a user clicks "Retry processing", when the request succeeds, then the document's status moves to `queued` without a page reload; when it fails, then a connectivity-safe error message is shown, never a raw exception.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (76/76 Vitest, 38/38 Playwright)
- [x] No requirement silently changed or reinterpreted
- [x] No spec file required a change — implementation matched `api.md`/`ui-ux.md` as written
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

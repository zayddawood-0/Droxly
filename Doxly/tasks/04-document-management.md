# Task 04: Document Management (Frontend)

## Task ID
P04-001

## Feature
Document Management — Upload, List, Viewer Shell, Rename, Delete, Tag

## Objective
Deliver the frontend half of roadmap Phase 4: presigned direct-to-storage upload, a filterable/sortable/paginated Documents list, a document viewer shell (metadata + action rail, content pane deferred to Phase 5), rename, delete, and tagging — all wired to the documented `/documents` and `/tags` API contracts via the existing BFF proxy. Consistent with every prior frontend phase in this track, no backend router exists yet for these endpoints; the app is built and tested against the real (currently backend-less) BFF, which returns genuine 502s, never a mocked success state.

## Specification References
- `requirements.md` §1.3 (`FR-DOC-001..008`) — the requirement set this task targets.
- `roadmap.md` Phase 4 — objectives, dependencies (Phases 2–3), explicit exclusion of the processing pipeline (Phase 5).
- `decisions.md` ADR-009, OQ-04, OQ-06, OQ-07 — upload/storage decisions (25MB size limit, plan quotas).
- `security.md` §3 — client-side + server-contract MIME/size validation expectations.
- `api.md` `/documents` and `/tags` domains — exact request/response shapes consumed by `lib/api/documents.ts` and `lib/api/tags.ts`.
- `ui-ux.md` §5–§6, §15 — Documents list, Upload dropzone/dialog conventions, File Upload Conventions.
- `database.md` — `documents`, `tags`, `document_tags` shape mirrored by the frontend's TypeScript types.

## Requirements
- `FR-DOC-001` (P0): Presigned upload — presign → direct PUT to storage → confirm, with client-side type/size rejection before any network call.
- `FR-DOC-002` (P0): Document list — paginated, sortable (date/name/size), filterable (status/tag), scoped to the authenticated user via the BFF/JWT (no client-supplied `user_id`).
- `FR-DOC-003` (P0, partial): Document viewer shell — metadata, status, action rail. Content rendering for `ready` documents is explicitly out of scope (depends on Phase 5's extraction pipeline) and shows a "coming soon" placeholder instead.
- `FR-DOC-004` (P1): Rename — non-empty name validation, updates display name only.
- `FR-DOC-005` (P0): Delete — soft-delete via `DELETE /documents/{id}`, confirmation dialog, immediate removal from the list on success.
- `FR-DOC-006` (P1): Tag documents — create/apply tags via `TagEditorDialog`, `document_tags` association.
- `FR-DOC-007` (P2): **Not implemented this task.** Bulk select/delete/tag was not built — deferred; no bulk-selection UI exists on `DocumentTable`/`DocumentCard`. Flagged explicitly rather than silently dropped.
- `FR-DOC-008` (P0, partial): Status visibility via `StatusBadge` (shared vocabulary component) and a cheap polling-capable `getDocumentStatus` endpoint function. Live polling/SSE wiring into the viewer is deferred to Phase 5, where the processing pipeline that actually drives status transitions lands.

## Dependencies
- Phase 2 (Auth) — the BFF proxy, `DoxlyApiError`/`isConnectivityError`, session-refresh interceptor, and the established Server/Client Component + typed-API-client conventions this task reuses unchanged.
- Phase 3 (Database) — the `documents`/`tags`/`document_tags` schema this task's TypeScript types mirror (backend router itself is not built in this task; only the schema shape is a dependency).

## Files Affected
- `components/providers/query-provider.tsx` — new — TanStack Query client (`staleTime: 30s`, `retry: 1`).
- `lib/constants/documents.ts` — new — size limit, accepted MIME/extension lists, plan quotas, `formatBytes`.
- `lib/api/documents.ts`, `lib/api/tags.ts`, `lib/api/users.ts` — new — typed functions for every `/documents`, `/tags`, `/users/usage` endpoint in `api.md`.
- `hooks/use-documents.ts`, `hooks/use-tags.ts`, `hooks/use-usage.ts`, `hooks/use-document-upload.ts` — new — TanStack Query hooks + the presign/PUT/confirm upload orchestrator.
- `lib/validation/documents.ts`, `lib/validation/upload.ts` — new — Zod schemas + client-side file validation.
- `lib/api/upload-transport.ts` — new — `XMLHttpRequest`-based PUT with progress events (fetch cannot report upload progress).
- `components/domain/documents/*` — new — `status-badge`, `file-type-icon`, `documents-empty-state`, `document-card`, `upload-dropzone`, `upload-file-row`, `upload-dialog`, `rename-dialog`, `delete-dialog`, `tag-editor-dialog`, `document-row-actions`, `document-table`, `documents-toolbar`, `usage-strip`.
- `app/(dashboard)/documents/*`, `app/(dashboard)/documents/upload/*`, `app/(dashboard)/documents/[documentId]/*`, `app/(dashboard)/dashboard/*` — new — route implementations.
- `app/layout.tsx` — modified — added `QueryProvider`.
- `e2e/documents.spec.ts` — new — real-BFF E2E coverage.

## Implementation Notes
- Direct-to-storage upload bypasses the BFF proxy for the PUT step only (`architecture.md` §4) — presign and confirm still go through it.
- One canonical `StatusBadge` status→label→color mapping is used everywhere status appears (list, card, viewer) — never a second ad-hoc mapping.
- `Select`'s Base UI primitive does not auto-derive a display label from `SelectItem` children; `Select.Value` needs an explicit `children` render function (or an `items` prop on `Select.Root`) or it silently renders the raw value string. This was found as a bug during this task (see Remaining Issues) and fixed in `documents-toolbar.tsx` — future `Select` usage elsewhere in the app should follow the same pattern.
- Multi-tenant isolation: every `lib/api/documents.ts` call relies on the BFF forwarding the verified session; no `user_id` is ever read from client state or passed as a request parameter.

## Tests
- Component/unit (Vitest + Testing Library + MSW) — `lib/constants/documents.test.ts`, `lib/validation/upload.test.ts`, `status-badge.test.tsx`, `upload-dropzone.test.tsx`, `upload-dialog.test.tsx` (presign→PUT→confirm success path, client-side unsupported-file rejection with no network call, one-file-failure-doesn't-block-another).
- E2E (Playwright, against the real backend-less BFF, per `testing.md`'s "no mocked success states" principle) — `e2e/documents.spec.ts`: documents-list connectivity error + retry, list/grid view toggle, upload dialog client-side rejection, upload dialog real-upload connectivity error, document-viewer connectivity error (not a blank page), full-page upload route parity with the dialog.
- Cross-tenant isolation: no dedicated frontend test — this category is owned by the backend router (not yet built) per `testing.md`; the frontend never has access to another tenant's `user_id` to even attempt a cross-tenant call.

## Acceptance Criteria
(Adapted from `requirements.md` §1.3, frontend-observable subset)
- Given a supported file type under the size limit, when selected in the Upload dialog, then presign → direct PUT → confirm run in sequence and the file row shows "Queued for processing" on success.
- Given an unsupported file type, when selected, then it is rejected client-side with a specific message and no `presign` request is ever made.
- Given N documents, when the Documents list loads, then it is paginated, sortable by date/name/size, and filterable by status/tag, with the active filter state reflected in the URL.
- Given a delete request on a document, when confirmed, then it is removed from the list/viewer immediately (query invalidation) and the viewer redirects to `/documents`.
- Given no reachable backend, when any of the above actions run, then the UI shows the shared connectivity-error message rather than a blank page, a raw exception, or a fabricated success state.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (70/70 Vitest, 38/38 Playwright)
- [x] No requirement silently changed or reinterpreted — `FR-DOC-007` (P2, bulk actions) explicitly not implemented and called out here rather than silently dropped or claimed done
- [x] No spec file required a change — implementation matched `api.md`/`database.md`/`ui-ux.md` as written
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

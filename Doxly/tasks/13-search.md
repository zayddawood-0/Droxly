# Task 13: Global Search (Frontend)

## Task ID
P13-001

## Feature
Global Search — Debounced Query, URL-State Filters, Grouped Highlighted Results, Command-Trigger Wiring

## Objective
Deliver the frontend for `FR-SEARCH-001`–`FR-SEARCH-003` per the approved frontend implementation plan's Phase 13 entry: a prominent debounced search input, a type/tag/status/date filter row that collapses into a mobile sheet, and a results list of document-level cards grouping highlighted matching snippets — reachable both from the sidebar and from the app-shell's global command trigger (⌘K/Ctrl+K), which had existed as inert UI since Phase 1. Built against `api.md`'s `/search` contract and tested against the real (currently backend-less) BFF proxy, consistent with every prior frontend phase.

## Specification References
- `requirements.md` §1.10 (`FR-SEARCH-001`–`FR-SEARCH-003`) — the requirement set this task targets.
- `ui-ux.md` §12 (Global Search) — this task's UI contract; no gap found.
- `ui-ux.md` §0 (App Shell) — "a command/search trigger (keyboard shortcut, opens Global Search)," wired for the first time in this task.
- `api.md` §8 (`/search`) — query/filter params, paginated result shape — **the `snippet` field's shape was amended during this task** (see Implementation Notes).
- `rag.md` §12 (Hybrid Search) — the keyword+vector fusion this UI's results are ranked by (backend, not built in this task).
- `security.md` §6.2, `CLAUDE.md` §6 — untrusted-document-content rendering rules, directly informing the snippet-highlighting design (see Implementation Notes).

## Requirements
- `FR-SEARCH-001` (P0): Search by keyword/semantic query across all owned documents; ranked results with highlighted snippets, strictly scoped to the caller.
- `FR-SEARCH-002` (P1): Filter results by document type, tag, date range, and processing status.
- `FR-SEARCH-003` (P1): Hybrid (full-text + vector) ranking — backend concern (`rag.md` §12); the frontend consumes the already-ranked, already-fused result order as-is.

## Dependencies
- Phase 4 (Document Management) — reuses `StatusBadge`'s status vocabulary (`STAGE_LABEL`, exported for the first time in this task) for the filter row's status options, and the citation-style `/documents/{id}?page=N` deep-link convention established there.
- Phase 7 (RAG) — the backend hybrid-search index this UI is built to consume once a backend `/search` router exists; not itself built in this task.
- Phase 9 (AI Chat) — the `page_number`/`snippet` citation deep-link pattern this task's result-click navigation mirrors exactly.

## Files Affected
- `specs/api.md` — modified — §8 `GET /search`: replaced the ambiguous `snippet: string (match highlighted)` with an explicit offset-based `SearchSnippet` shape (see Implementation Notes).
- `lib/api/search.ts` — new — typed `search()` function and result/snippet types.
- `hooks/use-search.ts` — new — `useSearchQuery` (query-gated on a non-empty `q`, `keepPreviousData` to avoid flicker between filter/page changes).
- `hooks/use-debounced-value.ts` — new — generic debounce hook.
- `components/domain/search/{search-input,filter-bar,highlighted-snippet,result-card}.tsx` — new.
- `components/domain/documents/status-badge.tsx` — modified — exported `STAGE_LABEL` so `FilterBar`'s status options reuse the one shared status vocabulary instead of a second copy.
- `app/(dashboard)/search/search-view.tsx` — new — debounced input + URL-synced filters + grouped results with pagination.
- `app/(dashboard)/search/page.tsx` — modified — wired `SearchView` in a `<Suspense>` boundary (was `PhasePlaceholder`).
- `components/layout/top-bar.tsx` — modified — the search trigger button (both desktop and mobile) now navigates to `/search`; a new `⌘K`/`Ctrl+K` global keydown listener does the same from anywhere in the authenticated shell.
- Tests: `hooks/use-debounced-value.test.ts`, `components/domain/search/{highlighted-snippet,result-card,filter-bar}.test.tsx`, `components/layout/top-bar.test.tsx` (extended).
- `e2e/search.spec.ts` — new.

## Implementation Notes
- **Spec gap resolved, with a real security implication:** `api.md`'s `snippet: string (match highlighted)` never specified the highlight markup format, while `ui-ux.md` §12 requires `<mark>` semantics. Since snippet text is a verbatim excerpt of a user-uploaded document — untrusted input per `CLAUDE.md` §6 and `security.md` §6.2's explicit XSS warning ("a PDF can contain a filename or extracted paragraph that is itself an XSS payload") — returning pre-built HTML for the client to inject via `dangerouslySetInnerHTML` would have been a real injection vector if a document's extracted text ever contained markup-like characters. Resolved by redefining the field as `SearchSnippet: { text: string, highlights: [{start,end}] }` — plain text plus character-offset ranges — so the client wraps matches in a real `<mark>` JSX element over properly-escaped text, never interpreting document-derived content as markup. Verified with a dedicated test asserting literal `<script>` text in a snippet renders as text, not a DOM element.
- **Result grouping is a spec-documented client responsibility, not an API gap:** the API returns one row per matching chunk (a document with several matches yields several rows sharing `document_id`), and `ui-ux.md` §12 already says "potentially multiple snippets per document" — `api.md` was clarified to state this explicitly, and `groupResultsByDocument()` implements the grouping client-side (scoped to the current page of results — not across pages, an accepted and documented trade-off).
- **Global command trigger wired for the first time:** `TopBar`'s search button existed since Phase 1 as inert placeholder UI (no `onClick`). This task wires it to `router.push("/search")` and adds a `⌘K`/`Ctrl+K` `keydown` listener at the same component (mounted on every authenticated page), satisfying `ui-ux.md` §0's "a command/search trigger (keyboard shortcut, opens Global Search)" — a simple navigation, not a new command-palette overlay component (none is named anywhere in the approved component architecture).
- **Debounce drives the fetch; the URL stays in sync as a side effect** — typed input updates local state immediately (so the input never feels laggy), a 400ms-debounced value drives `useSearchQuery`, and a `useEffect` mirrors the settled value into the URL's `q` param for shareable/bookmarkable links, matching the route table's "Client (debounced query, URL state)" description. Filters (type/tag/status/date) apply immediately on change, matching `ui-ux.md`'s "filters narrow results without re-navigating."
- **Client-side date-range guard:** `api.md` documents `422` for `date_from > date_to`; rather than let every such combination round-trip to a guaranteed error, the view detects it locally and shows an inline validation message instead of firing the request.
- **No new dependency for date inputs:** native `<input type="date">` rather than adding a date-picker library, consistent with `CLAUDE.md` §5's "unnecessary dependencies" avoidance — there was no existing date-picker component to reuse, and the native control satisfies the requirement.
- **Status vocabulary reuse:** `FilterBar`'s status filter options reuse `StatusBadge`'s `STAGE_LABEL` map (newly exported) rather than re-declaring the six status labels a second time — the one status vocabulary the app already committed to (`ui-ux.md`'s "Processing Indicators" consistency rule).

## Tests
- `hooks/use-debounced-value.test.ts` — settles only after the delay elapses with no further changes; an intermediate change resets the timer.
- `components/domain/search/highlighted-snippet.test.tsx` — matched range renders inside a real `<mark>` element; no highlights renders plain text; document text containing angle-bracket/script-like content is never interpreted as markup.
- `components/domain/search/result-card.test.tsx` — `groupResultsByDocument` groups same-`document_id` rows into one result; each snippet links to `/documents/{id}?page=N`, omitting the query param when there's no matched page.
- `components/domain/search/filter-bar.test.tsx` — `countActiveFilters`; "Clear filters" only appears once a filter is active and resets every field; the mobile Filters trigger shows an active-count badge.
- `components/layout/top-bar.test.tsx` (extended) — the search button and `Ctrl+K` both navigate to `/search`.
- E2E (`e2e/search.spec.ts`, 4 tests): the no-query empty state with example queries; submitting a query shows the real connectivity error, not a blank region; clicking an example query fills the input and searches; the search trigger and `Ctrl+K` both navigate to `/search`. All exercise the real backend-less BFF, per the established no-mocks pattern for E2E.

## Acceptance Criteria
(Adapted from `requirements.md` §1.10, frontend-observable subset)
- Given no query yet, then the page shows the "search across all your documents" empty state with example queries, distinct from a zero-results state.
- Given the user types a query, then results fetch after a debounce delay (not on every keystroke) and render as document-level cards with `<mark>`-highlighted snippets.
- Given a query with zero results, then a message names the query and suggests different terms or filters — visually distinct from the no-query-yet state.
- Given the user sets a type/tag/status/date filter, then results narrow without a full page navigation.
- Given `date_from` would be after `date_to`, then the view shows an inline validation message instead of firing a doomed request.
- Given the user clicks a result's snippet, then it navigates to that document at the matched page.
- Given the user presses `⌘K`/`Ctrl+K` or clicks the top-bar search trigger from any authenticated page, then they land on `/search`.
- Given no reachable backend, a search failure shows the shared connectivity-error handling with a retry, never a blank region.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (148/148 Vitest, 53/53 Playwright — one pre-existing, documented parallel-load flake in `route-smoke.spec.ts` unrelated to this task, confirmed passing in isolation)
- [x] No requirement silently changed or reinterpreted — the snippet-shape ambiguity was resolved explicitly in the spec, with its security rationale documented, before implementation
- [x] `specs/api.md` updated — the one spec change this task required, with rationale
- [x] Browser QA performed at desktop/mobile via mocked-network screenshots (real-BFF interactive states aren't reachable, consistent with prior phases); empty state, grouped/highlighted results, and the mobile Filters sheet all verified rendering correctly
- [x] Regression check performed across Phases 1–12 (navigation, auth, documents, chat, summarization, extraction, comparison, forms, API interactions, shared components, responsive layouts) — no regressions found; backend pytest 87/87, Docker Compose healthy
- [x] Basic performance review performed — no meaningful issues found (debounce prevents per-keystroke fetches, `keepPreviousData` avoids flicker on filter/page changes, tags query cache is shared with the Documents page's existing toolbar, no new dependencies added)
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

# Doxly — UI/UX Specification

> Concrete page-level and component-level specification for Doxly's interface. Brand personality and voice principles live in `design.md` — this file references them rather than re-deriving them. API contracts referenced here (e.g., "the documents list endpoint") are defined precisely in `api.md`. All requirement IDs reference `requirements.md`.

## 0. App Shell & Navigation

Authenticated pages share a persistent app shell: a left sidebar (collapsible on tablet, replaced by a bottom/hamburger nav on mobile) and a content region. The sidebar renders exactly the navigation given in the product brief, unchanged:

```
Doxly

⌂ Dashboard
▣ Documents
✦ AI Chat
◇ Extractions
⇄ Compare
⌕ Search
◉ Analytics

────────────

⚙ Settings
```

The active route is indicated by a filled icon/label state, not a heavy background block — consistent with the minimal brand direction in `design.md`. Admin is intentionally **not** in this list (see §15). Unauthenticated pages (Landing, Login, Register) use a separate marketing/auth layout with no sidebar.

Global elements available from any authenticated page: a command/search trigger (keyboard shortcut, opens Global Search), a user menu (avatar → profile/settings/logout), and a toast region (bottom-right) for async operation results (`FR-DOC-008` status changes, extraction/comparison completion).

---

## 1. Landing Page (public)

- **Purpose:** Convert visitors to registered users. Communicate the Upload → Understand → Ask → Extract → Compare → Search → Act loop.
- **Layout:** Marketing layout — top nav (logo, Login, Register CTA), hero section (tagline "Your docs, but smarter."), a visual walkthrough of the seven-step loop as a horizontal or stepped sequence, a features grid (Chat, Extract, Compare, Search — one card per pillar), a final CTA band, footer.
- **Components:** shadcn `Button` (primary CTA), `Card` (feature grid), simple icon set (Lucide) per pillar — no sidebar, no app-shell chrome.
- **Interactions:** CTA buttons route to Register; nav Login routes to Login. Feature cards are static (no modal/expansion) to keep the page lightweight and fast (`NFR-PERF-001`).
- **Loading states:** Static page, effectively no loading state beyond initial paint; hero renders without waiting on any authenticated data.
- **Empty/Error states:** N/A (no user data on this page).
- **Success state:** N/A — success is navigating onward.
- **Responsive behavior:** Single-column stacking on mobile; hero and feature grid reflow from 3-column to 1-column under 768px.
- **Accessibility:** Semantic heading hierarchy (one `h1`), all CTAs keyboard-reachable and labeled, sufficient contrast on hero text over any background treatment (`NFR-A11Y-001`).
- **Requirements served:** supports overall product adoption; no specific FR (pre-auth marketing surface).

## 2. Login

- **Purpose:** Authenticate an existing user. Serves `FR-AUTH-003` (Google OAuth), `FR-AUTH-004` (email/password).
- **Layout:** Centered auth card on a minimal background (no marketing chrome). Card contains: email field, password field, "Forgot password?" link, primary "Log in" button, divider, "Continue with Google" button, footer link to Register.
- **Components:** shadcn `Card`, `Input`, `Label`, `Button`, `Separator`.
- **Interactions:** Client-side validation (required fields, email format) before submit; submit disables the button and shows an inline spinner; on failure, a single generic inline error ("invalid email or password") per `NFR-SEC-006` — never field-specific ("email not found").
- **Loading states:** Button-level spinner during submit; page itself renders instantly (no server-side data dependency beyond auth check).
- **Empty states:** N/A (form starts empty by design).
- **Error states:** Inline generic credential error; network/server error shown as a dismissible banner above the form, not a blocking modal.
- **Success state:** Redirect to Dashboard on success; no visible success flash (`FR-AUTH-004`).
- **Responsive behavior:** Card is full-width with margin on mobile, fixed max-width (~400px) centered on desktop/tablet.
- **Accessibility:** Labeled inputs (not placeholder-only), visible focus rings, form submits on Enter, error text associated to the form via `aria-live` region (`NFR-A11Y-001`).

## 3. Register

- **Purpose:** Create a new account. Serves `FR-AUTH-001` (email/password), `FR-AUTH-003` (Google OAuth).
- **Layout:** Same auth-card pattern as Login. Fields: display name, email, password (with strength indicator), primary "Create account" button, divider, "Continue with Google," footer link to Login.
- **Components:** shadcn `Card`, `Input`, `Label`, `Button`, `Separator`, a custom `PasswordStrengthMeter` (segmented bar, non-decorative — reflects the actual policy: length + letter + number).
- **Interactions:** Real-time password strength feedback as the user types; submit blocked until minimum policy is met; on duplicate-email failure, the same generic non-revealing error pattern as Login (`NFR-SEC-006`) — never "email already registered."
- **Loading states:** Button-level spinner during submit.
- **Empty/Error states:** Field-level validation errors (format) shown inline immediately on blur; submit-level errors shown as a banner.
- **Success state:** Redirect to Dashboard with a persistent "verify your email" banner until `FR-AUTH-002` completes.
- **Responsive behavior:** Same as Login.
- **Accessibility:** Password strength meter has a text equivalent (not color-only) for screen readers and color-blind users (`NFR-A11Y-001`).

## 4. Dashboard (`⌂`)

- **Purpose:** Post-login home base — orientation and quick action, not a dense data page.
- **Layout:** App shell + content region with: a greeting header, a quick-actions row (Upload, Ask a question, Search — each a prominent button/card), a "Recent documents" section (last N documents as compact cards with status badges), a usage summary strip (storage used / plan, small and unobtrusive).
- **Components:** shadcn `Card`, `Button`, `Badge` (status), custom `UsageStrip`.
- **Interactions:** Clicking a recent document opens the Document Viewer; quick actions route to Upload / Chat / Search respectively.
- **Loading states:** Skeleton cards for "Recent documents" while the list endpoint resolves; quick-actions render immediately (static).
- **Empty state:** Zero-document accounts show a dedicated first-run empty state replacing "Recent documents" — illustration/icon, one sentence explaining the value loop, a single prominent "Upload your first document" CTA. This is a deliberately different layout from the populated state, not a greyed-out empty table.
- **Error state:** If the recent-documents fetch fails, an inline retry affordance in that section only — the rest of the dashboard (quick actions) remains usable.
- **Success state:** N/A (navigational hub).
- **Responsive behavior:** Quick-actions row wraps to a 2-column then 1-column grid on smaller screens; recent-documents cards stack.
- **Accessibility:** Landmark regions (`main`, section headings), quick-action buttons have descriptive accessible names, not icon-only.
- **Requirements served:** supports `FR-DOC-001` (upload entry), `FR-AI-001` (chat entry), `FR-SEARCH-001` (search entry).

## 5. Documents (`▣`)

- **Purpose:** Primary document management surface. Serves `FR-DOC-002` (list), `FR-DOC-006` (tagging), `FR-DOC-007` (bulk actions).
- **Layout:** App shell + toolbar (search-within, filter controls, sort dropdown, view toggle list/grid, "Upload" button) + document collection (table in list view, card grid in grid view) + optional selection toolbar that appears when rows are checked.
- **Components:** shadcn `Table` or `Card` grid, `DropdownMenu` (filters/sort/row actions), `Checkbox` (bulk select), `Badge` (status — see §"Processing Indicators" below), `Input` (search-within), `Dialog` (rename, delete confirmation, tag editor).
- **Interactions:** Filter by type/tag/status/date (`FR-DOC-002`); row actions (rename `FR-DOC-004`, delete `FR-DOC-005`, tag `FR-DOC-006`, download); bulk select → bulk delete/tag (`FR-DOC-007`); clicking a row opens the Document Viewer.
- **Loading states:** Skeleton rows/cards on first load; subsequent filter/sort changes show a lightweight inline loading indicator in the toolbar area rather than replacing the whole list (avoids layout jump).
- **Empty states:** Two distinct empty states — (a) truly zero documents (same guidance as Dashboard's empty state, "Upload your first document"), (b) zero results for the current filter/search combination ("No documents match these filters" + a "Clear filters" action). These must look different so users don't think they've lost all their data.
- **Error state:** List-fetch failure shows a full-region error card with retry, not a silent blank table.
- **Success state:** Toast confirmations for delete/rename/tag actions ("Document deleted," undo affordance where feasible within the soft-delete window per `privacy.md`).
- **Responsive behavior:** Table view collapses to card/grid view automatically below tablet width (a data table is not usable on a phone); filter toolbar collapses into a single "Filters" sheet/drawer on mobile.
- **Accessibility:** Table has proper header/row semantics; bulk-select checkboxes are individually labeled ("Select {file_name}"); status badges carry a text label, not color alone (`NFR-A11Y-001`).

## 6. Upload

- **Purpose:** Get a file from the user's device into processing. Serves `FR-DOC-001`, `FR-DOC-008`.
- **Layout:** Can be a dedicated route or a modal/drawer launched from Documents/Dashboard — spec assumes a modal for a lighter feel, with a full-page fallback route for direct linking. Content: a large dropzone (drag-and-drop + click-to-browse), a list of files staged/in-progress below it once selected.
- **Components:** custom `Dropzone`, `ProgressBar` per file, `Badge` (validation state), shadcn `Dialog` (if modal), `Button`.
- **Interactions:** Drag-over highlights the dropzone; file selection triggers immediate client-side validation (type via extension + a quick content check where feasible, size against the 25MB limit) **before** any network call; invalid files are rejected inline with a specific reason ("File exceeds 25MB limit" / "Unsupported file type — PDF, DOCX, TXT, CSV only") without blocking the other valid files in a multi-file selection; valid files proceed to presigned upload immediately with a per-file progress bar.
- **Loading states:** Per-file upload progress bar (0–100%) during the direct-to-storage PUT; a distinct "confirming…" micro-state between upload completion and the backend confirm call.
- **Empty state:** Default dropzone idle state ("Drag files here or click to browse").
- **Error state:** Per-file error state (validation failure, upload failure, confirm failure) shown inline on that file's row with a retry action; one file's failure never blocks others.
- **Success state:** Completed files transition to a "Queued for processing" state and link through to the Document Viewer (which then shows live `FR-DOC-008` status), or the modal closes and a toast confirms "3 documents uploaded" with a link to Documents.
- **Responsive behavior:** Dropzone remains usable via the click-to-browse fallback on mobile (drag-and-drop is a desktop enhancement, not a requirement).
- **Accessibility:** Dropzone is a real interactive element reachable by keyboard (Enter/Space opens the file picker), file list uses `aria-live` to announce progress/completion without spamming (`NFR-A11Y-001`).

## 7. Document Viewer

- **Purpose:** Inspect a single document and jump into any AI action on it. Serves `FR-DOC-003`.
- **Layout:** Two-region layout — a primary content pane (tabs or split: "Original" file preview and "Extracted Text" with page navigation) and a right-hand action rail (Chat about this document, Summarize, Extract, Compare, Export, Download original, Rename, Delete, Tags).
- **Components:** custom `PdfPreview`/`FilePreview`, `Tabs`, `PageNavigator`, action rail as a stack of `Button`s, `Badge` (status).
- **Interactions:** Page navigation syncs highlighted text region when arriving from a citation deep-link (from Chat, `FR-RAG-002`); action rail buttons route into Chat (pre-scoped to this doc), Extractions, Compare (with this doc pre-selected as Document A), Export.
- **Loading states:** If `status != ready`, the content pane is replaced by a processing-status view (stage indicator: extracting → chunking → embedding, using the shared status-badge vocabulary in §"Processing Indicators") instead of attempting to render partial/absent content.
- **Empty state:** N/A per se — a `failed` document shows its `processing_error` message and a "Retry processing" action (`FR-PROC-005`) in place of content.
- **Error state:** Same as above for `failed`; a transient viewer-load error (e.g., preview render failure) is scoped to the content pane with a retry, action rail remains usable.
- **Success state:** N/A (viewing is not itself a completed action).
- **Responsive behavior:** Action rail collapses to a horizontal scrollable button row (or a "..." overflow menu) below tablet width; original/extracted tabs stack full-width.
- **Accessibility:** Page navigation is keyboard-operable; tab panels follow WAI-ARIA tabs pattern.

## 8. AI Chat (`✦`)

- **Purpose:** Conversational document Q&A. Serves `FR-AI-001` through `FR-AI-006`, `FR-RAG-002`.
- **Layout:** Two-pane: a conversation list sidebar (within the page content area, separate from the global nav sidebar — collapsible) and the active thread (message list + composer fixed to the bottom). A scope selector sits above the thread (single document / multiple documents / all documents, per `FR-AI-002`).
- **Components:** custom `ConversationList`, `MessageBubble` (user vs. assistant variants), `CitationChip`, `StreamingIndicator`, `Composer` (textarea + send button + stop button), `DocumentScopePicker` (multi-select combobox).
- **Interactions:** Sending a message appends a user bubble immediately (optimistic) and streams the assistant response token-by-token (`FR-AI-005`); citation chips are clickable and deep-link to the Document Viewer at the cited page/snippet; "Stop" cancels an in-flight generation (`FR-AI-006`); "Regenerate" re-runs the last turn.
- **Loading states:** `StreamingIndicator` (subtle animated dots/cursor, not a full spinner that hides partial content) while tokens arrive; conversation list shows skeleton rows on first load.
- **Empty states:** No conversations yet → centered prompt suggestions ("Ask a question about this document," example queries) instead of a blank sidebar; an empty active thread (new conversation, no messages) shows the same prompt suggestions in the main pane.
- **Error state:** A failed generation shows an inline error bubble in place of the assistant response with a "Retry" action, not a lost message.
- **Success state:** N/A — the grounded answer itself is the success state; the `FR-AI-004` "I don't know" response uses a visually distinct (e.g., muted/outlined rather than filled) bubble style so users don't mistake a decline-to-answer for a confident answer.
- **Responsive behavior:** Conversation list becomes a slide-over drawer on mobile (thread is the primary view); composer remains fixed to the viewport bottom above the mobile keyboard.
- **Accessibility:** New messages are announced via `aria-live="polite"` without interrupting screen-reader users mid-stream on every token; citation chips have descriptive accessible names ("Citation: page 4"); composer is a proper `textarea` with Enter-to-send / Shift+Enter-for-newline documented via a visible hint (`NFR-A11Y-001`).

## 9. Summarization

> Added at Phase 10 implementation time — this section was missing entirely (the page list jumped from AI Chat §8 to Extractions, with no Summarization entry), a gap resolved here per `CLAUDE.md`'s SDD rules rather than implemented against an assumed shape. Not a standalone nav page — the approved frontend plan describes this as "a summary entry point from Viewer/Documents, type selector, polling result view," consistent with `FR-SUM-*` never appearing in `specs/roadmap.md`'s route/IA discussion as its own destination.

- **Purpose:** Get a quick, persisted summary of a document at a chosen detail level, and revisit past summaries without regenerating them. Serves `FR-SUM-001`, `FR-SUM-002`.
- **Layout:** A `Dialog` launched from two entry points — the Document Viewer's action rail ("Summarize") and each Documents-list row's overflow menu ("Summarize") — never a dedicated route. The dialog has two regions: a past-summaries list (type badge + relative date, newest first, per `FR-SUM-002`'s "never overwrites, always accessible") and a "Generate new summary" affordance with a type selector; selecting a past summary or a freshly-completed one shows its full content in the same dialog.
- **Components:** shadcn `Dialog`, `Select` (or a small segmented control) for `summary_type` (brief / detailed / bullet points), `Badge` for type + the shared `StatusBadge`-style processing indicator while a generation is in flight, a plain scrollable text region for summary content (bullet points rendered as a real list, not literal `-` characters).
- **Interactions:** "Generate" (disabled while another generation for this document is already `processing`) posts the request and immediately shows the new entry in the list in a processing state; the client polls `GET /summaries/{id}` (api.md §5 — no SSE for this workflow, it's a queued background job) until `status` leaves `processing`; clicking any list entry (past or freshly completed) shows its content inline, never navigating away from the dialog.
- **Loading states:** A processing entry shows the shared pulsing/animated status treatment (matching the Processing Indicators vocabulary in principle, though this is a job status, not a document pipeline status) with a short explanatory line ("Generating your summary — this can take a moment"), not a fake progress percentage.
- **Empty state:** No summaries yet for this document → the dialog opens directly to the type-selector/Generate view instead of an empty list with nothing to click.
- **Error state:** A failed generation shows inline on that list entry with the reason and a "Retry" action that re-submits the same type as a new request (per `FR-SUM-002`, retries never overwrite — a fresh row is created); a list-fetch failure shows a retry affordance in place of the list.
- **Success state:** The completed summary's content is shown in place of the processing indicator, with a toast ("Summary ready") only if the dialog was closed or the tab was backgrounded when it finished — not an intrusive toast while the user is already watching it complete.
- **Responsive behavior:** Uses the same shared `Dialog` every other dialog in the app uses (a responsive centered modal capped at `calc(100%-2rem)` width, not a sheet — no dialog in this codebase converts to a sheet at mobile width, so this one doesn't invent that pattern either); the past-summaries list and the content view stack vertically rather than side-by-side at any width — this dialog was never a two-pane layout.
- **Accessibility:** The type selector has a visible label, not placeholder-only; the processing→success transition is announced via `aria-live="polite"` once (on completion), not on every poll tick; Retry is keyboard-reachable and appears in the same tab order as the failed entry it belongs to.

## 10. Extractions (`◇`)

- **Purpose:** Turn a document into structured data. Serves `FR-EXT-001` through `FR-EXT-004`.
- **Layout:** Document + schema selection step (preset template gallery or "Custom schema" builder) followed by a results view once extraction completes: a field table (Field | Value | Confidence | Source | Edit).
- **Components:** `TemplateGallery` (cards: Invoice, Contract, Resume, Research Paper, per `FR-EXT-002`), custom `SchemaBuilder` (field name + type + required toggle, add/remove rows), `Table` for results, `ConfidenceBadge`, inline edit affordance per row (`FR-EXT-004`).
- **Interactions:** Selecting a template pre-fills the schema; "Run extraction" triggers the job and transitions to a results-pending state; editing a field value opens inline edit (not a separate modal) and persists on blur/confirm.
- **Loading states:** Results-pending state shows a progress indicator distinct from document-processing status (this is an AI job, not the ingestion pipeline) with an estimated-wait framing rather than a fake percentage.
- **Empty state:** No past extractions for this document → prompt to run one; schema builder starts with one blank field row.
- **Error states:** Extraction failure (job-level) shows a retry action; per-field `not_found` results are rendered in a visually distinct muted state with the reason text ("Not found in document") — explicitly **not** styled the same as a genuinely empty/blank value the user could confuse for a data gap they need to fill themselves (`FR-EXT-003`).
- **Success state:** Toast on completion ("Extraction complete — 8 of 10 fields found") summarizing coverage, not just a silent table refresh.
- **Responsive behavior:** Field table becomes a stacked card-per-field layout on mobile (label/value/confidence/source stacked, not a horizontally scrolling table).
- **Accessibility:** Editable cells are keyboard-operable (Enter to edit, Escape to cancel); confidence is conveyed with text/icon in addition to color.

## 11. Comparison (`⇄`)

- **Purpose:** Understand differences between two documents. Serves `FR-COMP-001` through `FR-COMP-003`.
- **Layout:** Document A / Document B picker (two document-select combobox inputs) → report view: a change-summary strip (counts by type) above a side-by-side (desktop) or unified (mobile) diff-style rendering with inline change-type badges.
- **Components:** `DocumentPicker` (×2), `ChangeSummaryStrip`, `DiffView` (side-by-side and unified variants), `ChangeTypeBadge` (addition/deletion/modification/factual/numeric/wording, each a distinct color+icon pairing).
- **Interactions:** Selecting both documents enables "Compare"; report supports filtering by change type; clicking a change scrolls/highlights the corresponding location in both documents (side-by-side view).
- **Loading states:** Report-pending state with progress framing similar to Extractions (background AI job, not ingestion).
- **Empty/degraded state:** When documents are too structurally different to align meaningfully (`FR-COMP-003`), the report view is replaced by an explicit message explaining why a meaningful diff isn't available, plus a fallback (e.g., "View both documents side-by-side without alignment") rather than forcing a misleading diff.
- **Error state:** Comparison job failure shows a retry action.
- **Success state:** Toast on completion; the report itself persists and is revisitable (not regenerated per view).
- **Responsive behavior:** Side-by-side collapses to unified/stacked diff on mobile and narrow tablet.
- **Accessibility:** Change-type badges carry text labels, not color alone; diff regions are navigable via a "next change" keyboard shortcut for long documents.

## 12. Global Search (`⌕`)

- **Purpose:** Find content across the user's whole corpus. Serves `FR-SEARCH-001` through `FR-SEARCH-003`.
- **Layout:** Prominent search input (also reachable via the global command trigger from §0) + filter row (type/tag/date) + results list (document-level cards with highlighted matching snippets, potentially multiple snippets per document).
- **Components:** `SearchInput` (debounced), `FilterBar`, `ResultCard` with `HighlightedSnippet`.
- **Interactions:** Debounced query-as-you-type results (`FR-SEARCH-001`); filters narrow results without re-navigating; clicking a result opens the Document Viewer scrolled/highlighted to the matching location.
- **Loading states:** Lightweight inline spinner in the search input area during debounce-triggered fetch, not a full-page loader.
- **Empty states:** Two distinct states — (a) no query yet ("Search across all your documents" with example queries), (b) query with zero results ("No results for '...' — try different terms or check your filters"). Must look different from each other.
- **Error state:** Inline retry within the results region.
- **Success state:** N/A (results themselves are the success state).
- **Responsive behavior:** Filter row collapses into a "Filters" sheet on mobile; results remain a single-column list at all sizes.
- **Accessibility:** Results count announced via `aria-live` on query change; snippet highlighting uses `<mark>` semantics, not color-only spans.

## 13. Analytics (`◉`)

- **Purpose:** Personal usage insight. Serves `FR-ANALYTICS-001` (and `FR-ANALYTICS-002` where applicable).
- **Layout:** A grid of compact stat cards (documents processed, storage used, AI requests this period) above one or two minimal charts (documents-over-time, AI requests-over-time) and a "most-used features" small list/bar.
- **Components:** `StatCard`, minimal chart components (line/bar — flat, no 3D/gradient decoration, consistent with brand restraint), `List`.
- **Interactions:** Period selector (7d/30d/90d) re-fetches chart data.
- **Loading states:** Skeleton stat cards and chart placeholders on load/period change.
- **Empty state:** New accounts with no activity show a "Nothing to show yet — your usage will appear here once you start uploading and asking questions" message instead of empty/zeroed charts that look broken.
- **Error state:** Inline retry per section (a stat-card fetch failure doesn't block the charts from rendering).
- **Success state:** N/A (informational page).
- **Responsive behavior:** Stat card grid reflows 4→2→1 columns; charts remain legible at mobile width (simplify tick density rather than shrinking illegibly).
- **Accessibility:** Charts have a text/table equivalent or accessible summary for screen-reader users, not visual-only data.

## 14. Settings (`⚙`)

- **Purpose:** Account, security, plan, and data control in one place. Serves `FR-USER-001/002/003`, `FR-AUTH-008`, `FR-SETTINGS-001`, `FR-EXPORT-004`.
- **Layout:** Sectioned single page (or sub-tabs): Profile, Security (sessions list, password change), Plan & Usage, Notifications, Data Export, Danger Zone (account deletion) — Danger Zone visually separated (border/color) and placed last.
- **Components:** `Form` sections (shadcn `Input`, `Label`, `Switch` for notification toggles), `SessionList` (device/browser/last-active + revoke action per `FR-AUTH-008`), `UsageStrip` (reused from Dashboard), `Dialog` with typed-confirmation input for account deletion (user types their email to confirm, per the destructive-action pattern in `security.md`).
- **Interactions:** Each section saves independently (no single giant "Save" button spanning unrelated sections); session revoke is immediate with a confirming toast; data export request triggers a background job with a "we'll email you when it's ready" acknowledgment (`FR-EXPORT-004`) rather than a blocking wait; account deletion requires the typed confirmation before the destructive action enables.
- **Loading states:** Per-section skeletons/spinners independent of each other.
- **Empty state:** Sessions list always has at least the current session; no meaningful empty state otherwise.
- **Error state:** Per-section inline error on save failure, field values are preserved (never cleared) on failure.
- **Success state:** Toast per successful save, scoped to the section that changed.
- **Responsive behavior:** Sections stack vertically on mobile; sub-tab navigation (if used) becomes a horizontal scroll or select dropdown.
- **Accessibility:** Danger Zone actions are not reachable by a single accidental keystroke (confirmation dialog required); form sections have proper fieldset/legend grouping.

## 15. Admin (role = `admin` only)

- **Purpose:** Internal operational tooling. Serves `FR-ADMIN-001` through `FR-ADMIN-003`. Explicitly **not** linked from the standard sidebar — reached via a distinct route guarded by role check, with a visually distinct (e.g., muted/utility) chrome so it never feels like a "power user" area of the consumer product.
- **Layout:** Simple internal-tool layout: a left tab set (Users, System Health) rather than the consumer sidebar; a suspend-confirmation dialog.
- **Components:** `Table` (user directory: email, plan, signup date, status — no content columns, enforcing `FR-ADMIN-001`'s explicit exclusion of document/chat/extraction content), `StatCard`/`Table` for queue depth and failure-rate metrics (`FR-ADMIN-002`), `Dialog` for suspend action (`FR-ADMIN-003`) with a required reason field logged to `audit_logs`.
- **Interactions:** Search/filter user directory by email/status; suspend action requires confirmation and immediately reflects the user's new status in the table (optimistic update reconciled on response).
- **Loading states:** Standard table skeletons.
- **Empty/Error states:** Standard table empty/error patterns, consistent with Documents table conventions.
- **Success state:** Toast confirming suspend action.
- **Responsive behavior:** Admin is designed desktop-first (internal tool, not a consumer mobile flow) but must remain usable at tablet width at minimum — no hard requirement for phone-optimized layout.
- **Accessibility:** Same baseline (`NFR-A11Y-001`) as consumer pages — internal tooling is not exempt.

---

## 16. Design System Foundations

### Typography
A single clean, modern sans-serif carries UI text (body, labels, data) at a restrained, legible scale (roughly 6–7 steps from small metadata text up to page headings) with consistent line-height tuned for scanning dense document/data content rather than long-form reading. Marketing surfaces (Landing) may pair a slightly more expressive sans for display headings, but never a decorative/script face — the brand is confident and modern, not playful-to-the-point-of-unserious. Numeric/data-heavy contexts (Analytics stat cards, extraction confidence scores, file sizes) use tabular figures so columns align.

**Concrete typefaces (implemented, Phase 1):** **Manrope** (700/800) for headings/display — self-hosted via `next/font/google`, exposed as the `font-heading` Tailwind token, applied by default to every `h1`–`h6`. **IBM Plex Sans** (400/500/600) for body/UI text — the `font-sans` default. **IBM Plex Mono** (400/500/600) for tabular/data contexts (file sizes, confidence scores, requirement IDs) — the `font-mono` token. Each declares a real system-font fallback stack (`ui-sans-serif, system-ui, sans-serif` / `ui-monospace, SFMono-Regular, Menlo, monospace`) so a font-load failure never breaks layout.

### Color System
A neutral-first palette (near-white/near-black surfaces with a graduated neutral scale for borders/muted text) plus **one** confident accent color used deliberately (primary actions, active nav state, links) rather than sprinkled decoratively — consistent with the brief's instruction to avoid unnecessary gradients/decoration. Semantic colors are reserved strictly for status meaning, not general decoration: a "processing" hue (informational/neutral-blue family), a "ready/success" hue (green family), a "failed/danger" hue (red family), a "warning" hue (amber family) — each paired with an icon/text label, never color alone (`NFR-A11Y-001`). Both light and dark mode are baseline requirements, not a stretch goal, expressed as semantic tokens (background/surface/border/text/muted-text/accent/success/warning/danger) rather than hardcoded values, so the same component vocabulary works in both themes.

**Concrete tokens (implemented, Phase 1 — `frontend/app/globals.css`):**

| Token | Light | Dark | Used for |
|---|---|---|---|
| `background` | `#f7f8fa` | `#0d0f13` | Page canvas |
| `card` / `popover` | `#ffffff` | `#15181d` | Cards, dialogs, dropdowns |
| `foreground` | `#14171c` | `#ebedf2` | Primary text |
| `muted-foreground` | `#5b6270` | `#9ca3b3` | Secondary/metadata text |
| `border` / `input` | `#dfe3e9` | `#282d36` | Hairlines, input borders |
| `primary` (accent) | `#2952cc` | `#7ea0ff` | Primary actions, active nav, links, focus ring |
| `accent` (subtle) | `#e8edfc` | `#1c2740` | Hover/active background fills |
| `success` | `#1f8a5f` | `#3fbe86` | `ready` status, positive confirmation |
| `warning` | `#b4740e` | `#e3ac46` | Caution states, low-confidence extraction |
| `danger` (`destructive`) | `#c4331f` | `#f17161` | `failed` status, destructive actions |
| `info` | `#3d6fd1` | `#7ea0ff` | `extracting`/`chunking`/`embedding` (in-progress) |

Every semantic color ships a paired `-soft` background tint (e.g. `success-soft`) for badge fills, so a status badge never relies on the raw saturated color as a large fill. Theme resolution follows the three-state contract every Doxly page must support: an explicit `data-theme="dark"`/`"light"` wins first, then `prefers-color-scheme`, with `system` as the default (no manual toggle shipped yet — deferred to the Settings page a later phase implements; `next-themes` already manages persistence so adding the toggle control is additive, not a re-architecture).

### Spacing, Radius, Shadow
Spacing follows Tailwind's default scale consistently (no ad hoc pixel values). Border radius uses one consistent scale across the app — soft rounding on cards/inputs/buttons, slightly tighter on data-dense elements like table cells — avoiding both sharp corporate rectangles and overly bubbly/playful shapes. Elevation is expressed with shadows sparingly (dialogs/popovers/dropdowns lifting off the page) — flat surfaces (cards, list rows) rely on borders or subtle background contrast rather than shadow, keeping the surface calm per the brief's explicit anti-clutter direction.

**Concrete scale (implemented, Phase 1):** base radius `0.625rem` (10px) on cards/dialogs/buttons via the `--radius` token, scaling down to `~6px` (`radius-sm`) for tighter data-dense elements (table cells, small badges) and up to `~14px`/`~18px` (`radius-xl`/`radius-2xl`) for larger surfaces — one token, several derived steps, never a hand-typed pixel value per component. Breakpoints are Tailwind's unmodified default scale: `sm` 640px · `md` 768px · `lg` 1024px · `xl` 1280px — adopted explicitly here to close the ambiguity of this section's earlier qualitative-only ("mobile"/"tablet") language. The persistent app sidebar (§0) uses this scale concretely: hidden below `md`, an icon-only rail from `md` to `lg`, the full labeled sidebar at `lg` and above.

### Core Components
- **Cards** (shadcn `Card`): the base container for document tiles, stat summaries, and dashboard sections — consistent padding/radius/border across every usage.
- **Buttons** (shadcn `Button`): a small set of variants (primary/accent, secondary/neutral, ghost, destructive) used consistently — destructive variant reserved exclusively for irreversible actions (delete, account deletion) so its color carries real meaning.
- **Inputs** (shadcn `Input`/`Textarea`/`Select`/`Combobox`): consistent label-above pattern, inline validation messaging, no placeholder-as-label anti-pattern.
- **Tables** (shadcn `Table`): consistent header styling, row hover state, and selection state reused across Documents, Extraction results, and Admin — one table visual language app-wide.
- **Dialogs** (shadcn `Dialog`): reserved for focused confirmations and short forms (rename, tag editor, delete confirmation) — never used for primary long-form flows like Extraction's schema builder, which lives inline in the page.
- **Toasts** (shadcn `Sonner`/`Toast`): the standard channel for async operation results (upload complete, processing complete, extraction complete, save confirmations) — bottom-right, auto-dismissing except for error toasts which persist until dismissed.
- **Navigation**: the persistent sidebar described in §0, plus contextual in-page navigation (tabs, sub-nav) that never duplicates or contradicts the global nav's information architecture.

### AI Chat Conventions
Assistant responses stream with a minimal animated indicator (not a generic three-dot "typing" cliché divorced from content — prefer a subtle cursor/caret at the end of the growing text). Citations render as small numbered or footnote-style chips inline with the claim they support, visually secondary to the answer text itself but always present and clickable — citations are a core trust signal for a document-grounded product, not a buried footer link. User and assistant messages are distinguished by alignment/subtle background difference rather than heavy chat-bubble skeuomorphism, keeping the surface calm and document-focused rather than looking like a generic consumer chat app.

### File Upload Conventions
The dropzone has four explicit visual states — idle, drag-over (accent border highlight), uploading (per-file progress), and error (per-file, non-blocking) — reused identically wherever upload appears (dedicated Upload flow, and any inline "add another document" affordance elsewhere).

### Processing Indicators
One `StatusBadge` component vocabulary is used everywhere a document's pipeline status appears (Documents list, Document Viewer, AI Chat's document-scope picker, Extraction/Comparison document pickers): `queued` (neutral/muted), `extracting`/`chunking`/`embedding` (informational, animated/pulsing to signal active work, collapsible into a single "Processing" label with a tooltip for the specific stage where space is tight), `ready` (success), `failed` (danger, with a tooltip/click-through to the sanitized error reason and retry action). This single vocabulary is a deliberate consistency requirement — no page invents its own status styling.

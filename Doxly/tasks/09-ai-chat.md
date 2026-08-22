# Task 09: AI Chat (Frontend)

## Task ID
P09-001

## Feature
AI Chat — Full Chat UI: Streaming, Citations, Scope Picker, Stop/Regenerate

## Objective
Deliver the frontend for conversational document Q&A per the approved frontend implementation plan's Phase 9 entry: a two-pane chat interface (conversation list + active thread), SSE token streaming, citation deep-links, a document-scope picker, and stop/regenerate controls — built against `api.md`'s documented `/chat` contract and tested against the real (currently backend-less) BFF proxy, consistent with every prior frontend phase in this track. No backend chat router is built in this task.

## Specification References
- `requirements.md` §1.6 (`FR-AI-001..006`) — the requirement set this task targets.
- `ui-ux.md` §8 (AI Chat) — layout, components, interactions, all four states, responsive behavior, accessibility — this task's primary UI contract.
- `api.md` §4 (`/chat`) — conversation CRUD, the SSE message-streaming contract, stop endpoint, and the regenerate endpoint added in this task (see Implementation Notes).
- `architecture.md` §5 — the inline (not queued) SSE request flow for Document Q&A.
- `langgraph.md` §2 — the Document Q&A graph's node sequence and citation-validation behavior this UI is built to consume once a backend exists.

## Requirements
- `FR-AI-001` (P0): Start a conversation about a document — composer + scope picker on `/chat`, creates a conversation on first send.
- `FR-AI-002` (P1): Multi-document / workspace-wide chat — `DocumentScopePicker` supports single, multi, and all-documents (workspace) scope.
- `FR-AI-003` (P0): Conversation history — `ConversationList` + persisted messages fetched via `GET /chat/conversations/{id}`, follow-up turns include prior history.
- `FR-AI-004` (P0): Graceful "I don't know" — a zero-citation completed assistant turn renders in the visually distinct muted/outlined bubble style.
- `FR-AI-005` (P1): Streaming responses — real SSE token-by-token rendering via `lib/api/sse.ts`'s `consumeEventStream`.
- `FR-AI-006` (P2): Regenerate / stop — both implemented; "stop" calls the documented stop endpoint and locally aborts the stream reader; "regenerate" required a new endpoint (see Implementation Notes).

## Dependencies
- Phase 2 (Auth) — BFF proxy, `DoxlyApiError`/`isConnectivityError`, typed-client conventions this task extends unchanged.
- Phase 4 (Document Management) — `useDocumentsQuery` reused by `DocumentScopePicker` to list `ready` documents.
- Phase 5 (Document Processing) — the app shell/status-UI patterns this phase's loading/error states follow.

## Files Affected
- `lib/api/client.ts` — modified — exposed `fetchWithRefresh` (session-refresh-and-retry returning the raw `Response`) so the SSE consumer reuses the exact same CSRF/refresh logic as every other endpoint, never duplicated.
- `lib/api/sse.ts` — new — `consumeEventStream`, the generic `text/event-stream`-over-POST parser (native `EventSource` can't POST a body).
- `lib/api/chat.ts` — new — typed functions for every `/chat` endpoint in `api.md`, plus `ChatStreamEvent` union.
- `hooks/use-conversations.ts`, `hooks/use-chat-stream.ts` — new — TanStack Query hooks + the send/regenerate/stop stream-orchestration hook.
- `components/domain/chat/*` — new — `citation-chip`, `streaming-indicator`, `message-bubble`, `composer`, `document-scope-picker`, `conversation-list`, `empty-thread-prompt`, `chat-thread`.
- `app/(dashboard)/chat/chat-view.tsx` — new — two-pane layout + mobile drawer.
- `app/(dashboard)/chat/page.tsx`, `app/(dashboard)/chat/[conversationId]/page.tsx` — modified — replaced the Phase-1 `PhasePlaceholder` scaffolding with `ChatView`.
- `specs/api.md` — modified — added the regenerate endpoint (see below).
- Tests: `lib/api/sse.test.ts`, `hooks/use-chat-stream.test.tsx`, `components/domain/chat/message-bubble.test.tsx`, `components/domain/chat/composer.test.tsx`, `e2e/chat.spec.ts`.

## Implementation Notes
- **Spec gap resolved:** `FR-AI-006`/`ui-ux.md` §8 require a "Regenerate" action, but `api.md` had no such endpoint. Added `POST /chat/conversations/{id}/messages/{message_id}/regenerate` to `api.md` §4 before implementing against it (same SSE contract as send-message; reuses the existing user turn rather than creating a duplicate one) — per `CLAUDE.md`'s SDD rule against silently inventing undocumented backend behavior.
- **SSE via `fetch`, not `EventSource`:** the chat endpoint is a `POST` with a JSON body; native `EventSource` only supports `GET`. `consumeEventStream` reads `response.body`'s `ReadableStream` directly and parses `event:`/`data:` frames.
- **One source of truth after a turn completes:** `useChatStream` layers an optimistic user bubble + streaming assistant draft on top of the server-persisted `messages` from `useConversationQuery`; on `done`, it invalidates the conversation query and clears local state, deferring to the server's authoritative row (real ID, citations) rather than keeping a permanently-parallel local copy.
- **A mid-stream `event: error` is data, not an exception** (api.md's own framing) — `runStream` tracks a `{current: DraftStatus}` ref (a plain `let` was over-narrowed by TypeScript's control-flow analysis across the async callback boundary) so a mid-stream error correctly skips the done-only `finish()` cache-invalidate, which would otherwise silently wipe the error bubble just shown to the user — caught by `hooks/use-chat-stream.test.tsx`'s error-path test.
- **Citation deep-links** point to `/documents/{id}?page=N`; the Document Viewer doesn't yet consume that query param (its content pane is still the Phase 4/5 "coming soon" placeholder) — a pre-existing, correctly-scoped limitation, not new to this task.
- **Layout fix:** the two-pane container's height was originally computed via a rough `vh` guess, leaving ~50px of unwanted whole-page scroll instead of a viewport-pinned composer (`ui-ux.md` §8's "composer fixed to the bottom"). Fixed by empirically measuring `PageShell`'s actual chrome (TopBar + `main` padding + `PageHeader` block) via the running app and correcting the `calc()` — found and fixed during this task's own browser QA pass.

## Tests
- `lib/api/sse.test.ts` — event-order parsing, non-2xx-before-stream-opens throws `DoxlyApiError`, mid-stream `error` event delivered to the callback without throwing.
- `hooks/use-chat-stream.test.tsx` — token accumulation → cache-invalidate-and-clear on `done`; mid-stream error surfaces on the draft without wiping it; conversation auto-creation on first send.
- `components/domain/chat/message-bubble.test.tsx` — grounded-answer citations, the FR-AI-004 muted/outlined "I don't know" style, streaming indicator visibility, inline error bubble + Retry, stopped-state label, Regenerate only on the last completed assistant message.
- `components/domain/chat/composer.test.tsx` — Enter sends, Shift+Enter inserts a newline, whitespace-only input never sends, Stop replaces Send while streaming, the Enter/Shift+Enter hint is visible.
- `e2e/chat.spec.ts` (real backend-less BFF) — composer/scope-picker render, send surfaces the connectivity error (not an unhandled rejection — the bug found and fixed above), conversation-list and unreachable-conversation connectivity errors, mobile drawer opens.

## Acceptance Criteria
(Adapted from `requirements.md` §1.6, frontend-observable subset)
- Given the `/chat` page, when a user sends a message with no existing conversation, then a conversation is created and the message streams into it.
- Given a conversation with prior turns, when the user asks a follow-up, then prior messages are visible above the new turn.
- Given a completed assistant turn with zero citations, then it renders in the distinct "I don't know" bubble style, never mistakeable for a confident answer.
- Given an in-progress generation, when the user clicks Stop, then the stream halts locally immediately and the backend is notified.
- Given a completed assistant turn, when the user clicks Regenerate, then a new response streams in for the same question.
- Given no reachable backend, every one of the above actions shows the shared connectivity-error message rather than a blank page, an unhandled rejection, or a fabricated success state.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (94/94 Vitest, 43/43 Playwright)
- [x] No requirement silently changed or reinterpreted — the regenerate endpoint gap was resolved by updating `api.md`, not by improvising
- [x] `specs/api.md` updated (regenerate endpoint) — the one spec change this task required
- [x] Browser QA performed at desktop/tablet/mobile; one real layout bug (composer not pinned, ~50px page overflow) found and fixed
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

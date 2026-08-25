# Task R4: Chat Integration

## Task ID
R4-001

## Feature
AI Chat — the Document Q&A conversational surface: conversation/message CRUD, the streaming `POST .../messages` endpoint, stop/regenerate, citations, and AI request observability, built on top of the already-tested `document_qa.py` LangGraph workflow, `RetrievalService`, and `CitationService`.

## Objective
Close the router/service integration gap `tasks/remediation-plan.md` §7 (R4) identifies: the LangGraph Document Q&A workflow, retrieval, and citation services exist and are unit-tested, but no HTTP layer exists at all. This task builds `chat_service.py` + `api/v1/routers/chat.py` so a user can actually hold a grounded, cited, streamed conversation about their documents.

## Specification References
- `tasks/remediation-plan.md` §7 (R4, Revision 2) — authoritative scope, including §7.1 (exact SSE contract) and §7.2 (`NFR-OBS-001` observability).
- `specs/requirements.md` §1.6 (`FR-AI-001..006`), §1.5 (`FR-RAG-001..003`, already implemented, consumed here).
- `specs/api.md` §4 (`/chat`) — full endpoint contracts, verbatim.
- `specs/architecture.md` §5 (AI Request Flow — Document Q&A), §6 (multi-tenancy enforcement points).
- `specs/langgraph.md` §1 (shared principles), §2 (Document Q&A graph — state/nodes/routing).
- `specs/ai.md` (full) — provider abstraction, model tiers, context/token management, error handling, hallucination mitigation.
- `specs/rag.md` (retrieval mechanics, already implemented — consumed, not re-implemented).
- `specs/security.md` §7 (prompt injection — already enforced inside `document_qa.py`, verified not re-implemented), §9 (system prompt protection), §10 (rate limiting).
- `specs/database.md` §3.7-3.10 (`conversations`, `conversation_documents`, `messages`, `citations`).
- `specs/observability.md` §4 (`ai_requests` logging, verbatim field mapping).
- `specs/testing.md` §4.1-4.3 (graph/RAG/citation tests, already exist), §3.3, §3.5.
- `skills/backend.md` §12 (inline-vs-queued: chat is the one workflow that runs inline).

## Requirements
- `FR-AI-001` (P0) — start a conversation, ask questions, grounded+cited streamed response.
- `FR-AI-002` (P1) — multi-document / workspace-wide chat.
- `FR-AI-003` (P0) — conversation history persists and is used as context.
- `FR-AI-004` (P0) — graceful "I don't know," no fabricated citation.
- `FR-AI-005` (P1) — streaming responses.
- `FR-AI-006` (P2) — stop / regenerate (implemented per `api.md`'s explicit endpoints, not gate-blocking).
- `FR-RAG-001/002/003` — already implemented (`RetrievalService`, `CitationService`, graph); consumed here, not re-implemented.
- `NFR-OBS-001` (P0) — every chat graph invocation logs one `ai_requests` row.
- `NFR-SEC-001` — multi-tenancy at every layer.
- `NFR-SEC-002`/AI rate limit tier — applied to the two message-sending routes.
- `NFR-SEC-007/008/009` — prompt injection defense, system-prompt non-disclosure, sanitized errors (all already enforced by the existing graph/error hierarchy — verified, not re-implemented).

## Dependencies
- R1 (auth, CSRF, rate limiting — `get_current_user`, `verify_csrf`, `rate_limit_ai`).
- R2 (documents — a conversation scopes to `ready` documents).
- R3 (document processing — a document must actually reach `ready` for chat to have anything to retrieve).
- Phase 6/7/8 (`chunking`/`embedding`, `RetrievalService`, `CitationService`, `document_qa.py` graph) — reused unmodified.

## Pre-Implementation Findings — Spec Gaps Identified (per `CLAUDE.md` §4, resolved explicitly, not silently)

1. **`messages.status` — missing from `database.md` §3.9, required by `api.md`'s own behavioral contract.** `api.md` requires the `stop` endpoint to persist the assistant message "marked `status='stopped'`" and the SSE `error` path to persist a partial message "flagged incomplete" — but `database.md`'s `messages` table has no `status` column, and neither does the `Message` model. This is a genuine spec-completeness gap (the endpoint behavior was specified in `api.md` without updating the owning schema table), not an invented requirement. **Resolution:** `database.md` §3.9 is updated in this same task to add `status TEXT NOT NULL DEFAULT 'complete', CHECK IN ('complete','stopped','incomplete')`, with a corresponding Alembic migration. This is the one schema change R4 makes.
2. **Chat message content length cap — `api.md` references "length-capped per `security.md` input limits," but `security.md` defines no specific number for chat messages.** No existing precedent field in this codebase caps free-text user content at a specific length (document/tag names cap at 500, an unrelated shape of field). **Resolution:** a `max_length=8000` cap is applied to `ChatMessageRequest.content` as an explicit, documented implementation decision — a generous but bounded ceiling consistent with `ai.md` §6's token-budget principle (prevents a single message from starving the context budget), not a spec-mandated number. Flagged here rather than silently chosen with no trace.
3. **Streaming architecture — how the graph's "streamed tokens" reach the SSE client without contradicting the Citation Validator's "post-processes the *completed* answer" gate.** `langgraph.md` §2 node 5 (Citation Validator) explicitly "post-processes the **completed** answer" and forces the safe fallback *after* generation if ungrounded (`ai.md` §8 point 1: checked "before a response is **returned**"). If raw provider tokens were relayed live to the SSE client during generation, an ungrounded answer would already be partially visible before the fallback could apply — defeating `FR-AI-004`'s absolute "no fabricated citation" guarantee (this codebase's own `ai.md` calls this "Doxly's core trust promise"). **Resolution (architecture decision):** `chat_service.py` does not treat `build_document_qa_graph(...).ainvoke(state)` as one opaque call. It composes the graph's own exported node functions directly (`classifier_node`, `citation_validator_node`, plus the canned `OUT_OF_SCOPE_RESPONSE`/`NO_ANSWER_RESPONSE` constants — all reused unmodified, zero duplicated logic, and `RetrievalService.retrieve()` called the same way `retriever_node` calls it), and for the Answer Generator step calls `LLMProvider.generate()` (not `.stream()`) to get the complete answer **plus its real `input_tokens`/`output_tokens`/`model` from the provider's own usage response** — deliberately choosing accurate `NFR-OBS-001` (P0) observability data over literally invoking `.stream()`, since `.stream()`'s token-delta interface has no accompanying usage-accounting channel and reimplementing token counting client-side would be a strictly worse, approximated substitute for data the provider already returns for free via `generate()`. The client-facing `event: token` stream is a chunked replay (word-by-word, mirroring `FakeLLMProvider.stream()`'s own established convention) of the final, already-safety-checked answer, not a live relay of unvalidated generation — full reuse of every tested node, the compiled graph (`build_document_qa_graph`) and its own tests remain completely untouched, and `FR-AI-004`'s guarantee holds without exception. Documented as a decision (not a silent choice) because it is genuinely consequential: `stop` can only interrupt the chunk-relay phase, not the LLM call itself (see Known Limitations), and `ai.md` §2's literal "`stream()` ... used only by the inline chat path" is knowingly not followed to the letter, in favor of the P0 observability requirement.
4. **Conversation title auto-generation — `database.md`/`api.md` say `title` is "auto-generated from first message" but no spec defines the algorithm.** **Resolution:** the first user message's content, truncated to 60 characters, is used verbatim as the title once the first message in a conversation is persisted — a simple, free, deterministic choice, not a new LLM operation (avoids inventing an unaccounted-for `ai_requests` operation/cost).

## Implementation Plan

### Files to create
- `backend/app/schemas/chat.py` — request/response Pydantic models per `api.md` §4, verbatim shapes.
- `backend/app/services/chat_service.py` — conversation CRUD + the streaming turn orchestration described above.
- `backend/app/core/chat_stream_control.py` — the Redis-backed stop-signal mechanism (new — no prior ADR covers cross-request/cross-replica signaling for an in-flight inline stream; documented as ADR-024, extending the already-established Redis usage rather than inventing a new store, consistent with `NFR-SCALE-001`'s stateless-replica requirement).
- `backend/app/api/v1/routers/chat.py` — the six `/chat` endpoints.
- `backend/alembic/versions/xxxx_messages_status.py` — the one schema change (see Gap 1).
- Tests: `test_chat_service.py`, `test_chat_api.py`, `test_chat_sse.py`, `test_chat_stop_regenerate.py`, `test_chat_observability.py` (exact filenames may consolidate during implementation; scope is what matters).

### Files to modify
- `backend/app/models/conversation.py` — add `Message.status`.
- `backend/app/repositories/conversation_repository.py` — extend `ConversationRepository` (list_paginated, soft_delete, get-with-scope), `MessageRepository` (list_for_conversation, get preceding user message for regenerate, update-on-stop/error), keep `CitationRepository`/`ConversationDocumentRepository` as-is (already sufficient).
- `backend/app/main.py` — mount `chat.router`.
- `specs/database.md` — §3.9 `status` column (Gap 1).
- `specs/decisions.md` — ADR-024 (stop-signal mechanism), ADR-025 (streaming architecture decision, Gap 3), backdated note nowhere needed (these are genuinely new R4 decisions).

### Explicitly NOT modified
- `app/ai/graphs/document_qa.py` — zero changes; every node reused as-is via direct import.
- `app/services/retrieval_service.py`, `app/services/citation_service.py` — zero changes.
- `app/ai/llm.py` — zero changes (`stream()` already exists exactly as needed).
- Anything under R2/R3's document pipeline.

## Architecture Decisions
1. **Streaming design** — see Gap 3 above. This is the single most consequential decision in this task; flagged explicitly rather than silently implemented.
2. **Stop signal via Redis, not an in-process registry** — a `stop` request may land on a different API replica than the one streaming the response (`NFR-SCALE-001`: stateless, horizontally-scalable API containers). A plain in-process `dict[message_id, asyncio.Event]` would silently fail to signal across replicas. `core/chat_stream_control.py` sets a short-TTL Redis key (`chat_stop:{message_id}`) that the streaming loop polls between chunks/nodes; `stop` fails open the same way `rate_limit.py`/`core/queue.py` already do (`decisions.md` ADR-021/023 precedent) — a Redis outage means `stop` silently doesn't take effect rather than 500ing the request, logged as a warning.
3. **AI request observability written directly in `chat_service`**, immediately after the (graph-composed) generation completes or raises — matching remediation-plan.md §7.2 exactly ("not deferred to a background job, since the metadata is already in hand"). Uses the existing `AiRequestRepository.create()` (`observability_repository.py`), unmodified.
4. **History bounding** — the most recent messages (oldest-first) are included up to a fixed token budget (reusing `document_processing/chunking.py`'s `count_tokens`, the same tokenizer already used for the embedding model, rather than a second token-counting implementation), older turns dropped entirely. `ai.md` §6's fuller "summarize older turns into a compact running note" refinement is **not** implemented — a deliberate, proportionate scope decision (it requires an additional LLM call with its own cost/latency/failure-mode surface that no requirement's acceptance criteria explicitly mandates), recorded under Known Limitations, not silently dropped.
5. **Conversation title auto-generation** — see Gap 4.

## API Contracts (verbatim from `api.md` §4 — restated here for implementation traceability, not redefined)
- `POST /chat/conversations` → 201, `409 document_not_ready`, `404`.
- `GET /chat/conversations` → paginated list, `updated_at desc`.
- `GET /chat/conversations/{id}` → detail + ordered messages + citations.
- `DELETE /chat/conversations/{id}` → 204, soft delete.
- `POST /chat/conversations/{id}/messages` → SSE (`message_id`→`token`*→`citations`→`done`|`error`), AI rate limit, `404`/`409 document_not_ready`/`429` pre-stream.
- `POST .../messages/{message_id}/stop` → `{message_id, status:"stopped"}`, `404`/`409 not_in_progress`.
- `POST .../messages/{message_id}/regenerate` → same SSE contract, echoes existing user `message_id`, AI rate limit.

## Security Requirements
- Every route: `get_current_user` (never a client-supplied `user_id`).
- Every mutating route: `verify_csrf`.
- `messages`/`.../regenerate`: `rate_limit_ai` (AI tier + daily cap).
- Every repository call user_id-first, owner-scoped; cross-tenant access to a conversation/message/document → `404`, never `403`, never a distinguishable error.
- Retrieval scoped to the caller's own `ready` documents only (delegates entirely to the already-tenant-scoped `RetrievalService`).
- No prompt/response content ever logged or included in `ai_requests` (verified against the existing graph's own discipline, not re-implemented).

## Testing Strategy
Per `testing.md` §3.3/§3.5 and this task's own new SSE-contract category:
1. Conversation create/list/detail/delete, incl. `document_not_ready`/cross-tenant 404.
2. Full SSE event-sequence assertion for a successful turn (`message_id`→N×`token`→`citations`→`done`, in order) — asserts actual payload shapes, not just that *a* stream occurred.
3. Mid-stream failure → `error` event + a persisted `status='incomplete'` message.
4. `stop` halts an in-flight stream, persists partial content with `status='stopped'`; `409 not_in_progress` on an already-finished message.
5. `regenerate` echoes the existing user message's ID, appends a new assistant row, walks back correctly to find the preceding user turn.
6. Citation persistence/shape correctness; workspace/multi-document scope disambiguation.
7. `ai_requests` row written on both success and failure paths, correct `operation="chat"`, no content fields.
8. Cross-tenant: conversation, message, and retrieval-through-chat isolation (the RAG-layer check happens before generation, not only at the HTTP layer).
9. Rate limiting (AI tier) on the two message-sending routes.
10. Regression: full existing suite (R1/R2/R3) unaffected.

## Acceptance Criteria
Copied from `specs/requirements.md` §1.6:
- `FR-AI-001`: Given a `ready` document, when the user sends a message, then a `conversations` row (if new) and a `messages` row are created, the graph runs, and a grounded, cited response streams back.
- `FR-AI-002`: Given multiple selected documents, retrieval spans only those; citations disambiguate the source document.
- `FR-AI-003`: Given a follow-up question, the workflow has access to prior turns (bounded).
- `FR-AI-004`: Given an unrelated question, the response states the documents don't contain the information, no fabricated citation.
- `FR-AI-005`: Responses stream rather than waiting for full completion.
- `FR-AI-006`: A user can stop an in-progress generation or regenerate the last answer.

## Definition of Done
- [ ] Code implements the Objective and satisfies all Acceptance Criteria
- [ ] Tests listed above are written and passing
- [ ] No requirement silently changed or reinterpreted — every gap above resolved explicitly
- [ ] `specs/database.md`, `specs/decisions.md` updated in this same review
- [ ] Full backend suite, ruff, black, mypy all green (see Final Report)
- [ ] Linked in the PR description with requirement IDs — pending PR creation (not requested this session)

## Known Limitations (recorded, not silently dropped)
- `stop` can only interrupt the chunk-relay phase (post-generation), not the LLM call itself — a direct, documented consequence of the safety-first streaming design (Gap 3). The LLM call for a single turn is typically a few seconds; this is judged an acceptable trade-off for a P2 requirement against a P0 anti-hallucination guarantee.
- Conversation history is bounded by hard truncation (drop oldest beyond the token budget), not `ai.md` §6's fuller "summarize into a running note" behavior.
- The `ai-eval` golden-set regression suite (`testing.md` §4.5/§4.6, hallucination/prompt-injection adversarial sets) is explicitly **R11's** deliverable per the remediation plan, not R4's — not built here.
- No frontend changes — `frontend/lib/api/chat.ts` already expects exactly this contract (verified by direct inspection) and needs none.

## Verification Results

- **Full backend test suite:** 329 passed, 0 failed (`pytest -q`) — 292 pre-R4 + 37 new R4 tests.
- **Ruff / Black / Mypy:** all clean.
- **Alembic:** `upgrade head` / `downgrade -1` / `upgrade head` all clean against a real Postgres instance.
- **Live smoke test:** real Postgres/Redis (Docker) + real uvicorn process, driven over genuine HTTP (not `ASGITransport`): register → login → create conversation → list → send message (12 real HTTP chunks observed, confirming genuine progressive SSE delivery) → get detail (title auto-generated, both messages persisted) → regenerate (echoes user message id, appends a 3rd row) → delete (soft-delete, 404 afterward) → `/stop` on an unknown message → `404`. All passed.
- **Two real bugs found and fixed during test-writing, not by trusting the design on paper:**
  1. `citation_validator_node`'s grounded-answer branch relies on LangGraph's own partial-state-merge semantics (it doesn't return `draft_answer` when grounded) — `chat_service.py` was initially treating its return value as a standalone result, causing a `KeyError` on every successful, grounded turn. Fixed by merging into `state`, matching the graph's actual contract.
  2. `get_preceding_user_message`'s `<` timestamp comparison failed to find the correct prior user message whenever a turn's user+assistant messages were written in the same transaction (Postgres's `now()` is transaction-scoped, not per-statement) — which is the **common case**, not an edge case, since one HTTP request is one transaction. Fixed to `<=`. Caught by `test_regenerate_echoes_user_message_id_and_appends_new_assistant_row`, not by inspection.

Full pass/fail detail and the complete file/architecture summary: see the Final Report delivered at the end of this implementation session.

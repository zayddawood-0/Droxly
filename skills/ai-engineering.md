# Doxly — AI Engineering Skill

> How to build AI features on Doxly well. `specs/ai.md`, `specs/langgraph.md`, and `specs/rag.md` define **what** the AI system does — provider abstraction, the four LangGraph workflows, and retrieval mechanics. This file defines **how** to work within that design without eroding it: the habits that keep the abstraction real, the grounding guarantees intact, and every AI call observable.

## Purpose

Doxly's core promise is grounded, cited answers over a user's own documents — not a generic chatbot bolted onto a file store. Every practice below exists to protect that promise: an AI feature that bypasses the shared abstraction, skips citation validation, or hand-rolls a new retrieval query is a regression even if it "looks like it works" in a demo.

## 1. LLM abstraction

**Practice:** all model calls go through the `LLMProvider` interface (`specs/ai.md`, `specs/decisions.md` ADR-011). Application code — LangGraph nodes, services — never imports a provider SDK directly.
**Best practice:** add a new provider by implementing the interface once, not by branching call sites on `if provider == "openai"`.
**Common mistake:** reaching for the Anthropic/OpenAI SDK directly "just for this one feature" because the abstraction doesn't yet expose a needed parameter — extend the interface instead.
**Quality bar:** every LLM call is mockable at the interface boundary in tests (`skills/testing.md` §Mocking discipline), never mocked at the raw HTTP layer.

## 2. Prompt design

**Practice:** prompt templates are centralized, versioned artifacts, not inline strings scattered across services and nodes.
**Best practice:** keep system instructions and document/user content structurally separate — document content is always injected into a clearly delimited data slot, never concatenated into the instruction text itself (this is the engineering-practice complement to `specs/security.md`'s prompt injection defense).
**Common mistake:** growing a prompt indefinitely with edge-case instructions instead of handling the edge case in code (validation, routing) where it's testable and cheap.
**Quality bar:** a prompt change is reviewable as a diff and re-run against the golden set (`specs/testing.md`) before merge.

## 3. Structured outputs

**Practice:** extraction and any schema-shaped output use the provider's native structured-output / tool-calling feature first, then Pydantic validation as a mandatory second gate — never trust either alone.
**Common mistake:** asking the model for "JSON only" in free text and regex-parsing the response; this is fragile and has no schema guarantee.
**Quality bar:** malformed output is caught by validation and routed to the failure/`not_found` path (`FR-EXT-003`), never silently coerced into something that looks valid.

## 4. Tool calling

**Practice:** tools exposed to a node have narrow, well-typed inputs/outputs and the minimum capability the node actually needs — least privilege, matching `specs/security.md`'s framing (a tool the Extraction Agent uses cannot, for example, delete data or call another user's resources).
**Common mistake:** giving a node a general-purpose "run any query" tool for convenience — this is exactly the kind of over-broad capability that turns a prompt-injection attempt into a real incident instead of a no-op.

## 5. RAG

**Practice:** chunking and embedding logic lives once, in the document-processing/AI layer described in `specs/rag.md` — never reimplemented per feature.
**Practice:** retrieval always goes through one shared, tenant-filtered retrieval function. A new feature that needs "find relevant chunks" calls that function; it does not write a new pgvector query.
**Quality bar:** because tenant filtering lives in exactly one place, `NFR-SEC-001` for retrieval is verified once and can't regress per-feature — this is the entire reason the shared function is mandatory, not a style preference.

## 6. Embeddings

**Practice:** batch embedding calls (many chunks per provider request), never one chunk per API call in a loop — matches `specs/rag.md`/`specs/performance.md`.
**Practice:** every embedding row records `embedding_model` (`specs/database.md` §3.4) at write time — never leave it to be inferred later.

## 7. Vector search

**Practice:** always call through the shared retrieval function (see RAG above). A hand-rolled `<=>` query in a new code path is a code review blocker, not a style nit — it's a likely tenant-isolation gap waiting to happen.

## 8. Context management

**Practice:** estimate/measure tokens before sending a request; when a document or conversation history exceeds budget, truncate or summarize predictably (oldest-first drop, or a summarization pass) — never a silent mid-sentence cut that produces a broken prompt.
**Quality bar:** context-budget behavior is deterministic and testable, not "whatever the provider's context window happens to allow this week."

## 9. Hallucination mitigation

**Practice:** every LLM call meant to produce a grounded answer passes through the Citation Validator node (`specs/langgraph.md`) before its output reaches the user — no exceptions for "quick" features.
**Quality bar:** an answer with a factual claim and zero supporting citations is treated as a bug in the golden test suite (`specs/testing.md`), not a UI styling edge case to paper over.

## 10. AI evaluation

**Practice:** the golden test set (`specs/testing.md`) is a first-class, reviewed artifact — changes to it go through the same review as code.
**Practice:** run it before merging any change that touches a prompt, model choice, or chunking strategy — these are exactly the changes most likely to silently degrade quality.

## 11. Prompt injection defense

**Practice (code review checklist item):** for any new or modified prompt template, ask explicitly — *does this ever concatenate raw document or user-supplied content into a position the model could interpret as an instruction?* If yes, redesign the template before merge, don't ship it with a caveat.
**Cross-reference:** `specs/security.md` §10–11 owns the full policy; this is the day-to-day enforcement habit.

## 12. AI observability

**Practice:** because every AI call is required to go through the shared provider abstraction, that is also where centralized logging and the `ai_requests` row (`specs/database.md` §3.13) get written. A feature that bypasses the abstraction silently loses observability and rate limiting at the same time — this is precisely why the abstraction is mandatory rather than a convenience wrapper.

## LangGraph node authoring checklist

Before adding a new node to any of the four graphs in `specs/langgraph.md`:

- [ ] Single responsibility — the node does one identifiable thing, not "classify and also retrieve."
- [ ] Typed state in/out — the node reads and writes only the state fields it needs to, documented.
- [ ] LLM calls isolated behind the `LLMProvider` interface — mockable in a unit test with no real network call.
- [ ] Explicit error/retry behavior — what happens on a transient provider error vs. a permanent content error is defined, not left to whatever the default exception path does.
- [ ] Unit tested with the LLM mocked, covering both the success path and at least one failure/retry path, before wiring into the graph.
- [ ] If the node produces a claim shown to the user, it passes through (or feeds into) the Citation Validator before reaching the response.

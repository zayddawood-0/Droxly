# Task 08: LangGraph — Four Stateful AI Workflows (Backend)

## Task ID
P08-001

## Feature
LangGraph — Document Q&A, Summarization, Extraction, and Comparison graphs

## Objective
Build the LangGraph state-machine scaffolding and all four graphs' nodes/routing per `roadmap.md` Phase 8, using the real `langgraph` library (`decisions.md` ADR-004 — mandatory, not hand-rolled orchestration), wired to a mockable `LLMProvider`. Every node is independently unit-tested with the LLM mocked, and every graph is ready to be invoked from an API endpoint — no endpoint is built this task (that's Phases 9–12). No frontend deliverable (confirmed as the same backend-only exception used for Phases 3, 6, and 7, applied directly given that established precedent).

## Specification References
- `langgraph.md` (full) — the exact state/node/routing contract for all four graphs; this task's primary spec.
- `ai.md` §2–3 — `LLMProvider` interface contract, model-tier abstraction, model selection table.
- `decisions.md` ADR-004 (LangGraph mandatory), ADR-011 (`LLMProvider`, Anthropic default), OQ-02 (model IDs, resolved this task).
- `testing.md` §4.1–4.3 — node-test scope (LLM mocked), RAG/retrieval test scope, citation test scope.
- `rag.md`, via Phase 7's `RetrievalService`/`CitationService`, reused rather than reimplemented inside graph nodes.

## Requirements
- Enables `FR-AI-*`, `FR-SUM-*`, `FR-EXT-*`, `FR-COMP-*` — graphs built here; product-facing endpoints wired in Phases 9–12 (roadmap.md's own framing, not a completion claim for those FR IDs yet).
- `NFR-MAINT-002`: every LangGraph node is independently unit-testable with the LLM call mocked.

## Dependencies
- Phase 6 (Embeddings) — `EmbeddingProvider`, reused directly by the Comparison graph's Semantic Alignment node.
- Phase 7 (RAG) — `RetrievalService`/`ContextItem`/`AssembledContext`/`CitationInput`, reused directly by the Document Q&A graph's Retriever node and the Extraction graph's grounding calls, rather than reimplemented.

## Files Affected
- `pyproject.toml` — modified — added `langgraph`.
- `app/core/config.py` — modified — `llm_provider`/`anthropic_api_key` settings.
- `app/ai/llm.py` — new — `LLMProvider`, `FakeLLMProvider`, `AnthropicLLMProvider`, `get_llm_provider()`, `ANTHROPIC_MODEL_IDS`.
- `app/ai/graphs/__init__.py`, `app/ai/graphs/document_qa.py`, `app/ai/graphs/summarization.py`, `app/ai/graphs/extraction.py`, `app/ai/graphs/comparison.py` — new.
- `tests/test_llm_provider.py`, `tests/test_graph_document_qa.py`, `tests/test_graph_summarization.py`, `tests/test_graph_extraction.py`, `tests/test_graph_comparison.py` — new.
- `specs/decisions.md` — modified — OQ-02 status resolved.

## Implementation Notes
- **Context Analyzer (Q&A) and Validation (Extraction) are deliberately thin, routing-only nodes.** Their documented substantive work (rank/dedupe/trim for Context Analyzer; Pydantic validation for Validation) already happens inside Phase 7's `RetrievalService.retrieve()` and `LLMProvider.generate_structured()`'s Pydantic gate, respectively. Reimplementing that logic a second time inside the node would duplicate it (CLAUDE.md §5's DRY rule) — the node's remaining, genuinely distinct job is the conditional-edge routing decision the spec separately calls out for it.
- **Extraction and Comparison take already-extracted text as explicit inputs/via retrieval**, not by reading from a document-processing pipeline — no such pipeline exists yet (Phase 5's backend extraction was never built in this session; only its frontend status UI was). Same "take the missing upstream stage as a parameter" pattern used in Phase 6/7.
- **Checkpointing uses `MemorySaver`** (in-process, not durable) for the three background-worker graphs. `langgraph.md` §1.7 mandates checkpointing but not a specific backend; no RQ worker or durable checkpoint store exists yet to checkpoint against across process restarts. A durable (Postgres/Redis-backed) checkpointer is a follow-up once that worker infrastructure is built.
- **Citation Validator's groundedness check is a word-overlap heuristic**, not a semantic verification LLM call. This is an explicit, documented simplification — production-quality grounding verification is a prompt/evaluation-methodology concern owned by `ai.md` §10's golden-set gating, not something this graph-shape task invents.
- **`ALIGNMENT_CONFIDENCE_THRESHOLD = 0.5`** (Comparison graph) is this implementation's chosen parameter — `langgraph.md` §5 says "a defined threshold" without specifying a number, so this is a calibratable constant, not a spec deviation.

## Tests
- `test_llm_provider.py` — `FakeLLMProvider`/`AnthropicLLMProvider` behavior, `get_llm_provider()` config branching.
- `test_graph_document_qa.py` — classifier/citation-validator node units, plus full-graph routing: out-of-scope short-circuit, empty-context short-circuit (`FR-RAG-003`), grounded answer with citations, forced fallback on ungrounded generation.
- `test_graph_summarization.py` — content-analyzer strategy selection, plus full-graph routing: first-try pass, retry-then-pass, exhausted-retry-budget failure (`langgraph.md` §3's "3 total attempts"), map-reduce path.
- `test_graph_extraction.py` — schema-precedence node units, `ExtractedField`'s never-fabricate guarantee, plus full-graph routing: classify→resolve→extract, generic-schema fallback, structural-failure retry-then-succeed, terminal failure after two structural failures.
- `test_graph_comparison.py` — content-extraction presence check, plus full-graph routing: aligned + classified diff, graceful degradation for unrelated documents (`FR-COMP-003`), missing-text failure, unmatched-segment-becomes-addition.
- All node/graph tests use `FakeLLMProvider`/`FakeEmbeddingProvider` exclusively — no live LLM/embedding API call in this layer, per `testing.md` §4.1/§4.2.

## Acceptance Criteria
(Adapted from `langgraph.md`'s per-graph routing/Definition-of-Done language)
- Given an out-of-scope query, the Document Q&A graph responds without calling Retriever or Answer Generator.
- Given a query with no relevant chunks, the graph responds "I don't know" without calling Answer Generator (`FR-RAG-003`).
- Given a generated answer that doesn't overlap the retrieved context, Citation Validator forces the safe fallback rather than returning it as-is.
- Given a summary that fails quality checks, the graph retries up to 2 times before terminal failure; a passing summary reaches success at any attempt.
- Given extracted fields the model can't locate, they're returned as `found=false` with a reason — never a fabricated value (`FR-EXT-003`).
- Given two structurally unrelated documents, Comparison returns a degraded-but-successful report rather than a misleading diff (`FR-COMP-003`).
- Every node above is directly callable and testable in isolation, with the LLM mocked (`NFR-MAINT-002`).

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (87/87 backend pytest)
- [x] No requirement silently changed or reinterpreted — the routing-only-node pattern, the heuristic grounding check, and the `MemorySaver` checkpointer choice are all explicitly documented as scoped decisions, not silent gaps
- [x] `specs/decisions.md` updated (OQ-02 resolved) — the one spec change this task required
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

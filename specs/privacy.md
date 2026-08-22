# Doxly — Privacy Specification

> Defines data ownership, lifecycle, and third-party handling. `security.md` owns access-control *mechanics* (who can reach what); this file owns data *lifecycle* (how long it exists, what happens when it's deleted, and where it travels to third parties). `observability.md` owns the exhaustive never-log field list; this file states the governing principle.

## 1. Data Ownership

Every piece of tenant data — `documents`, `document_chunks`, `conversations`, `messages`, `citations`, `extractions`, `comparisons`, `tags` — is owned exclusively by the `user_id` on its row, or transitively through its parent (e.g., a `document_chunks` row is owned by whoever owns its `documents.user_id`, per `database.md`). Doxly's engineering posture is to treat uploaded content as belonging to the user, used only to provide the requested product functionality (processing, chat, extraction, comparison, search) — never repurposed (e.g., for model training) without separate explicit consent, which is not offered in the MVP.

**Explicit gap:** this document is an engineering specification, not a substitute for a legally drafted Terms of Service or Privacy Policy. Those must be produced with legal counsel before public launch; this spec defines the technical behavior counsel's language should describe accurately, not the other way around.

## 2. User Isolation

Isolation is enforced at the DB/repository/API layers as described in `architecture.md` §6 and `NFR-SEC-001` (full mechanics: `security.md`). This file adds one privacy-specific extension: isolation guarantees must also hold for data **at rest outside live queries** — database backups, any data export tooling, and analytics aggregation. A backup restore procedure or an admin analytics query must not become a side channel that bypasses `user_id` scoping; any tooling that reads across all users (e.g., admin aggregate views per `FR-ADMIN-002`) operates only on aggregate/metadata columns, never content (`NFR-PRIV-004`).

## 3. Data Retention

| Data category | Retention while account active | After deletion trigger |
|---|---|---|
| Documents, chunks, embeddings | Indefinite, subject to plan storage quota (`decisions.md` OQ-07) | Soft-deleted immediately on user action (`FR-DOC-005`); hard-purged (object storage + `document_chunks` rows) within **30 days** |
| Conversations, messages, citations | Indefinite | Same as above when the underlying document(s) or account is deleted |
| Extractions, comparisons | Indefinite | Hard-purged with the account, or when the source document(s) are hard-purged |
| `ai_requests` (metadata only, no content) | Indefinite while useful | Purged after **~90 days** — retained only long enough to support cost/abuse investigation |
| `audit_logs` (metadata only, no content) | N/A (append-only) | Purged after **~1 year** — longest retention as a security incident trail; not tied to the user's content-deletion cycle since it contains no document/chat content |

The 30-day hard-purge window on document deletion exists to allow **support-assisted** recovery from an accidental deletion — Doxly does not ship a self-service "trash/undo" feature in the MVP UI (explicit scope boundary; a full versioning/trash feature is a `roadmap.md` Post-MVP candidate, not silently implied by this window).

## 4. Document Deletion (`FR-DOC-005`)

Deleting a document sets `documents.deleted_at`, which immediately excludes it from every list, search, and RAG-retrieval query (repository-layer filter, consistent with `NFR-SEC-001`'s enforcement pattern). The background hard-purge job then removes the object storage file and cascades (`ON DELETE CASCADE`, per `database.md`) through `document_chunks`.

**Deliberate trade-off — citation snippets survive chunk deletion:** `citations.document_chunk_id` is `ON DELETE SET NULL` rather than `CASCADE` (per `database.md`). This means a past chat message's citation `snippet` text remains visible in that conversation's history even after its source chunk has been purged following a single-document deletion — the conversation stays coherent rather than developing holes. This is intentional: conversation history integrity is prioritized over instantaneous, total content removal for the *single-document-delete* case specifically. It does not weaken account-level privacy: a full account deletion (`FR-USER-002`) purges `citations` rows themselves along with everything else, so no content outlives the account.

## 5. Account Deletion (`FR-USER-002`)

1. On confirmed request, `users.status` is set to `pending_deletion` immediately — login is blocked from that moment, before any data purge completes.
2. A background job cascades deletion through every owned table: documents (+ object storage), chunks, conversations/messages/citations, extractions, comparisons, tags, refresh tokens.
3. The purge completes within the same 30-day window as single-document deletion (§3); the user receives a confirmation email once the purge job completes.
4. `audit_logs` rows where the deleted user is the *actor* are retained per the audit retention cycle (security trail), but with the account itself unrecoverable and unable to authenticate.

## 6. Data Export (`FR-EXPORT-004`)

A full account export is a background job (not a synchronous request — exports can be large) producing a downloadable archive containing: document metadata and original files, extraction results (`result_json`), comparison results (`result_json`), and conversation transcripts (messages + citations). This satisfies data-portability expectations without requiring the user to reconstruct their content from individual per-feature exports (`FR-EXPORT-001/002/003`).

## 7. AI Provider Data Handling (`NFR-PRIV-003`)

- Only the **minimum necessary content** is sent to the LLM/embedding provider per call: retrieved chunks relevant to the current query (not entire documents dumped into context), and a bounded window of conversation history (per `ai.md`'s context management), not the full account history.
- Provider API accounts are configured to the **most restrictive data-retention / no-training option** each provider offers at the API tier (distinct from consumer-product defaults) — this is a required configuration step in `deployment.md`'s environment setup, not an optional hardening step.
- No user content is ever used to fine-tune a model, for Doxly's own use or a provider's, without explicit separate opt-in consent — not offered in the MVP, so in practice this never happens today.

## 8. Logging Restrictions

Governing principle (`NFR-PRIV-001`): **document content and chat content are never logged in plaintext**, in any environment, including debug/development logging paths.

Never logged: document content (extracted text or raw bytes), chat message content, extracted field *values* (field names/schema are fine; the values found are not), full embedding vectors, raw uploaded file bytes.

Safe to log: resource IDs (`document_id`, `user_id`, `conversation_id`), status enums, token counts, latency measurements, provider/model identifiers, error codes/categories (not raw exception messages that might embed content).

The exhaustive, canonical never-log field list and log-schema definitions live in `observability.md` — this section states the rule that governs it, not the full enumeration.

## 9. Third-Party Subprocessors

| Category | Purpose | Data exposed |
|---|---|---|
| LLM provider (Anthropic Claude, default) | Chat, summarization, extraction, comparison generation | Retrieved document excerpts + current query + bounded conversation history |
| Embedding provider (OpenAI, default) | Vector embedding generation | Document chunk text |
| Object storage (Vercel Blob, default) | Raw file storage | Original uploaded files |
| Transactional email provider | Verification, password reset, deletion confirmation emails | Email address, name, transactional content only |
| Google OAuth | Social login | Email, name, avatar (per OAuth consent scope) |

This list mirrors the provider choices in `decisions.md`, framed here from a "who has access to what data" angle rather than an architecture angle.

## 10. Children's Privacy

Doxly targets students, developers, researchers, freelancers, and young professionals — it is not designed or marketed for children under 13. A standard age-gate at registration (13+, or the higher threshold required by applicable regional law, e.g., GDPR-K considerations in some jurisdictions) is a **Post-MVP legal/compliance item** requiring counsel confirmation, not an engineering decision made silently in this spec. No COPPA-specific data-handling features are built in the MVP because the product is not directed at that age group.

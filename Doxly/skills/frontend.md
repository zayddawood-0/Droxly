# Doxly — Frontend Engineering Standards

> Deep-dive craft guidance for Next.js/React/TypeScript work on Doxly. Complements `specs/ui-ux.md` (what to build) and `specs/design.md` (why it should feel that way) — this file is about how to build it well.

## 1. Next.js App Router

File-based routing under `app/`. Route groups separate layout concerns without affecting the URL: `app/(auth)/` for login/register (minimal chrome), `app/(dashboard)/` for the authenticated shell (nav, sidebar). Use `loading.tsx` for route-level skeleton states, `error.tsx` for route-level error boundaries, `not-found.tsx` for 404s — every route segment that fetches data should define at least `loading.tsx`; every route segment with meaningful failure modes should define `error.tsx`.

## 2. Server Components vs. Client Components

Default to Server Components. A component becomes a Client Component (`"use client"`) only when it needs `useState`/`useEffect`/event handlers/browser APIs. Concretely: the document list, the dashboard stats, the settings page shell are Server Components fetching data server-side; the chat interface, the upload dropzone, and any form are Client Components. Push `"use client"` as far down the tree as possible — a page shouldn't become a Client Component just because one button inside it needs an `onClick`.

## 3. TypeScript

- Strict mode required (`strict: true`); no `any` without an inline comment explaining why.
- Shared request/response types mirror `specs/api.md` exactly — treat a type mismatch between frontend and the documented API contract as a bug in one of the two, not a reason to loosen the type.
- Discriminated unions for state, not booleans: a document's status is `'queued' | 'extracting' | 'chunking' | 'embedding' | 'ready' | 'failed'` (matching `database.md`), never a pair of `isProcessing`/`isReady` flags that can go out of sync.

## 4. Component architecture

```
components/
  ui/           # shadcn/ui primitives (button, dialog, input, toast...)
  domain/       # Doxly-specific composed components (DocumentCard, CitationChip, StatusBadge, ChatMessage)
  layout/       # nav, sidebar, page shells
```

Domain components are the reuse boundary that enforces `specs/design.md`'s "one visual language" rule — a `StatusBadge` used in the documents list and in the chat sidebar is the same component, not two similar-looking ones. Colocate a component's test next to it (`DocumentCard.tsx`, `DocumentCard.test.tsx`).

## 5. TailwindCSS

Utility-first, backed by a small shared token config (colors, spacing scale, radii) sourced from `specs/ui-ux.md`'s visual system — never hand-typed magic values (`px-[13px]`) scattered through class strings. Avoid heavy `@apply` abstraction layers that just recreate a second styling language on top of Tailwind; if a class combination repeats constantly, it belongs in a component, not a `@apply` rule.

## 6. shadcn/ui

Used as the primitive layer (buttons, dialogs, inputs, toasts, dropdowns) customized via the Tailwind config, not forked/copy-pasted and diverged per use site. Keep primitives thin — Doxly-specific behavior (a citation chip's expand/collapse, a status badge's color-by-state mapping) is composed on top in `components/domain/`, not baked into a modified copy of the primitive.

## 7. Forms

React Hook Form + Zod schema validation. Zod schemas mirror backend Pydantic validation rules field-for-field (same length limits, same regex, same required/optional shape) so a client-side error and a server-side error never disagree about what's valid.

## 8. Validation

Client-side validation is a UX convenience, never a security boundary — the backend (`skills/backend.md`, `specs/security.md`) is the sole authority. Every client-validated field is re-validated server-side regardless.

## 9. API communication

A thin typed API client module (`lib/api/`) wraps every backend call — no scattered raw `fetch()` calls in components. The client maps the backend's error envelope (`specs/api.md`) into typed errors the UI can branch on, and every call site handles loading/error/success uniformly rather than inventing a new pattern per feature.

## 10. State management

- **Server state** (documents, conversations, extractions): a data-fetching/caching library (TanStack Query) — handles caching, revalidation, and loading/error state without manual `useEffect` fetch boilerplate.
- **Client-only UI state** (a dialog's open/closed state, a form's draft value): local component state (`useState`) or, if genuinely cross-cutting, a light context — avoid introducing a heavy global state library without a concrete need that server-state caching and local state can't cover.

## 11. Error handling

Route-segment error boundaries (`error.tsx`) catch rendering failures; API client errors are caught at the call site and rendered in Doxly's brand voice (`specs/design.md` §1.4) — never a raw stack trace, error code, or "Something went wrong" with no next step.

## 12. Loading states

Skeleton loaders for content shape (not a bare spinner) for anything with a predictable shape (a document list, a chat history). For document processing specifically (`FR-DOC-008`), show the actual pipeline stage (`queued → extracting → chunking → embedding`), not a generic "Loading…" — the user should always know what's happening, not just that something is.

## 13. Empty states

Every list/collection view (documents, conversations, extractions, comparisons, search results) has a designed empty state per `specs/design.md` §6 — copy that states the one next action, never a bare "No items."

## 14. Responsive design

Mobile-first Tailwind breakpoints. The core loop (upload, chat, search, document viewing) is a required manual check at mobile width before a PR touching those flows is considered done — not an afterthought caught in a later pass.

## 15. Accessibility

Semantic HTML first (`<button>`, `<nav>`, `<main>`, proper heading hierarchy); ARIA attributes only to fill real gaps semantic HTML can't cover. Every interactive flow (upload, chat, dialogs) must be fully keyboard-operable, and dialogs/modals must manage focus (trap focus while open, return focus on close).

## 16. Performance

Route-segment code splitting is automatic with the App Router — don't fight it with unnecessary dynamic imports. Use `next/image` for every image. Avoid client-side data-fetching waterfalls (a component that fetches, then renders a child that fetches again) — prefer parallel or server-side fetching. Be deliberate about adding a heavy client-side dependency; check its bundle impact before merging.

## 17. SEO

Relevant to the public landing/marketing pages, not the authenticated dashboard. Use the Metadata API for titles/descriptions/OpenGraph tags, keep heading structure semantic (one `<h1>` per page), and ensure the landing page is server-rendered (it already is, by default, as a Server Component route).

## Recommended folder structure

```
app/
  (auth)/
    login/
    register/
    verify-email/
  (dashboard)/
    dashboard/
    documents/
      [documentId]/
    chat/
      [conversationId]/
    extractions/
    compare/
    search/
    analytics/
    settings/
  (admin)/
    admin/
  api/                    # Next.js Route Handlers (BFF proxy only)
components/
  ui/                     # shadcn/ui primitives
  domain/                 # DocumentCard, CitationChip, StatusBadge, ChatMessage, UploadDropzone
  layout/                 # Sidebar, TopNav, PageShell
lib/
  api/                    # typed API client
  types/                  # shared request/response types (mirrors specs/api.md)
  utils/
hooks/
```

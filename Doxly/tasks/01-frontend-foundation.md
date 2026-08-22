# Task P01: Frontend Foundation

## Task ID
P01-001..005

## Feature
Foundation — Frontend application bootstrap

## Objective
Stand up a TypeScript-strict Next.js (App Router) application with Tailwind CSS and shadcn/ui installed, the approved design tokens encoded as the Tailwind theme, the top-level route-group layout shells in place (empty), and a typed API client foundation — so every subsequent phase (Auth UI, Documents, Chat, …) has a consistent base to build on. This is the frontend slice of `specs/roadmap.md` Phase 1 (backend/DB/Redis scaffolding is out of scope for this task — a separate, non-frontend effort).

## Specification References
- `CLAUDE.md` §8 — no code before this task file existed; §5 coding principles (KISS, no premature abstraction)
- `skills/frontend.md` §1–§11, §17, recommended folder structure — App Router conventions, Server/Client split, component architecture, API client pattern, state management defaults
- `specs/ui-ux.md` §0 (app shell/navigation), §15 (design system foundations — narrative only, no token file exists; this task's design-token work is the resolution)
- `specs/decisions.md` ADR-001 (Next.js/React/TypeScript), ADR-005 (`/api/v1` versioning, referenced by the client foundation)
- `specs/architecture.md` §2.1 (Next.js is presentation + BFF only — never calls Postgres/Redis/LLM directly)
- `specs/security.md` §6.3 (CSRF double-submit token attached by the BFF layer)
- `specs/performance.md` §1 (Server Components by default, `next/font`, route-level code splitting)
- `specs/roadmap.md` Phase 1 (expected outputs: both apps boot locally; empty landing page shell)

## Requirements
- None directly — Phase 1 is infrastructure-only per `roadmap.md`; this task enables all subsequent FR-*/NFR-* work.

## Dependencies
- None (first frontend task).

## Files Affected
- `package.json`, `tsconfig.json`, `next.config.ts`, `tailwind.config.ts`, `postcss.config.mjs` — new
- `app/layout.tsx`, `app/page.tsx`, `app/globals.css` — new
- `app/(auth)/layout.tsx`, `app/(dashboard)/layout.tsx`, `app/(admin)/layout.tsx` + placeholder route pages per the route tree in the approved plan — new
- `components.json` + `components/ui/*` (shadcn primitives) — new
- `components/layout/*` (stub Sidebar/TopBar) — new
- `lib/api/client.ts`, `lib/types/errors.ts` — new
- `Dockerfile`, `docker-compose.yml` (frontend service only — backend/Postgres/Redis services added in a later, non-frontend task) — new
- `specs/ui-ux.md` §15 — modified (concrete token table replacing narrative-only description)

## Implementation Notes
- Server Components by default; `"use client"` only where Phase 1 genuinely needs interactivity (there is none yet — this phase is structural).
- Design tokens are the plan's proposed palette/type pairing, explicitly marked as a recommendation pending confirmation, not a silent final decision (`CLAUDE.md` §4.3).
- No feature logic (auth, documents, etc.) is implemented in this task — route pages are placeholders only.
- Docker Compose in this task covers the frontend service only; it is explicitly incomplete (no backend/DB/Redis) and will be extended, not replaced, when backend scaffolding begins.

## Tests
- Build/lint — `next build` and `next lint` succeed with zero errors.
- Route smoke — every placeholder route returns 200 (or the expected auth-group render) via a Playwright smoke check.
- Component smoke — installed shadcn primitives render without error (Vitest + RTL).

## Acceptance Criteria
- A fresh clone + one documented command (`npm install && npm run dev`, or `docker compose up`) boots the frontend locally.
- `npm run build` and `npm run lint` both succeed.
- All three route groups render their placeholder shells without runtime errors.
- Light and dark themes both render legibly using the token set.

## Definition of Done
- [x] Code implements the Objective and satisfies the Acceptance Criteria
- [x] Tests listed above are written and passing
- [x] No requirement silently changed or reinterpreted — the design-token gap was resolved by updating `specs/ui-ux.md` §15 in this same change, not improvised silently
- [x] `specs/ui-ux.md` updated (§15 token table)
- [ ] Linked in the PR description with phase (Phase 1) — pending actual PR creation

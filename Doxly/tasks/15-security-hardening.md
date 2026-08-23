# Task 15: Security Hardening (Frontend)

## Task ID
P15-001

## Feature
Frontend Security Hardening — Security Headers (CSP/HSTS/X-Frame-Options), CSRF Verification, XSS Audit, Cross-Tenant Denial UX Audit, Admin Role Guard

## Objective
Deliver the frontend scope of Phase 15 per the approved frontend implementation plan: "CSP/CSRF verification against real frontend requests, cross-tenant denial UX audit (does a foreign document URL render a clean not-found, never a broken page)." Unlike Phases 9–14, this is a verification-and-hardening pass across everything already built in Phases 1–14, not a new-feature build — apply `security.md`'s checklist, close gaps found under focused review, and treat "we verified it's already correct" as a legitimate, valuable outcome where that's what's true.

## Specification References
- `security.md` §11.3 (`NFR-SEC-011`) — security headers, this task's primary new implementation.
- `security.md` §6.3 (`NFR-SEC-010`) — CSRF double-submit token, verified (already correctly implemented in Phase 1/9's `lib/api/client.ts` and the BFF proxy — no changes needed).
- `security.md` §6.2 — XSS/output-encoding, audited (one `dangerouslySetInnerHTML` found, verified safe, informed the CSP design).
- `security.md` §3.2 — the "404, not 403" cross-tenant pattern, audited across every resource-detail route.
- `security.md` §3.1 — admin role check, a genuine gap found and closed (see Implementation Notes).
- `decisions.md` — **ADR-018 amended, OQ-12 added** during this task (see Implementation Notes).

## Requirements
No new `FR-*`/`NFR-*` requirement — this task verifies/hardens the existing `NFR-SEC-*` set (`NFR-SEC-001`, `-002`, `-003`, `-005` through `-011`) as it applies to the frontend, per `roadmap.md` Phase 15's framing: "closing gaps found under focused review rather than assuming each phase's inline security work was exhaustive."

## Dependencies
- Phases 2–14 (everything this phase reviews).

## Files Affected
- `specs/decisions.md` — modified — added **OQ-12** (nonce-based CSP `script-src`: tried, found broken under this project's production build configuration, reverted with rationale — see Implementation Notes).
- `next.config.ts` — modified — added `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security` response headers (none existed before this task).
- `lib/api/users.ts` — modified — added `getCurrentUser()` / `CurrentUser` / `UserRole` (previously only `getUsage()` existed).
- `hooks/use-current-user.ts` — new — `useCurrentUserQuery`.
- `components/layout/admin-guard.tsx` — new — the role guard closing the gap described below.
- `app/(admin)/admin/layout.tsx` — modified — now renders `AdminGuard` instead of the unguarded `AdminShell` directly.
- `components/layout/admin-shell.tsx`, `components/layout/top-bar.tsx` — modified — comments updated to reflect the guard now exists (both previously said "role check wired in Phase 2/15").
- `e2e/route-smoke.spec.ts` — modified — the `/admin` redirect test rewritten to assert the guard's fail-closed state instead of the pre-guard "always redirects" assumption (see Implementation Notes).
- Tests: `components/layout/admin-guard.test.tsx` (new).

## Implementation Notes

### 1. Security headers — a real, previously-total gap, now closed
`next.config.ts` had no `headers()` at all before this task — `security.md` §11.3's four headers (CSP, `X-Content-Type-Options`, `X-Frame-Options`, HSTS) didn't exist anywhere in the frontend. Added all four.

**The CSP `script-src`/`style-src` include `'unsafe-inline'` — a deliberate, documented trade-off, not an oversight.** A per-request nonce (Next.js 16's actual documented pattern for this — see `node_modules/next/dist/docs/.../file-conventions/proxy.md`; `middleware.ts` is deprecated in this Next.js version, renamed to `proxy.ts`, exactly the kind of version drift `AGENTS.md` warns about) was implemented, and verified working correctly under `next dev` via a real browser (no CSP console violations, hydration succeeds). It **failed under this project's actual production configuration** (`output: "standalone"` + Turbopack, `next build && next start` — the exact setup `playwright.config.ts`'s `webServer` and the Dockerfile both use): several of Next.js's own static `<script src>` tags in the production HTML aren't nonce-stamped, so the nonce'd policy blocks the app's own hydration scripts and the app never becomes interactive. This reproduced consistently across multiple clean rebuilds — confirmed via the full E2E suite failing 44/55 with CSP violation messages in the console — not a one-off flake. Reverted to `'unsafe-inline'` and documented the investigation as **`decisions.md` OQ-12**, to revisit once Next.js's Proxy-nonce support stabilizes for this build configuration, rather than ship a CSP that breaks the app for an unproven security gain.

The residual risk of `'unsafe-inline'` is low here specifically: the XSS audit performed alongside this change (grep for `dangerouslySetInnerHTML` across the entire frontend) found exactly **one** use — `components/ui/chart.tsx` (the shadcn Recharts wrapper, `decisions.md` ADR-018) — and its interpolated content is always this app's own static `ChartConfig` objects, never document- or user-derived. There is no known code path today that would let an attacker get their own inline script onto the page even with this directive relaxed. Every other directive stays fully restrictive (`default-src 'self'`, no external script/style/image/font/connect origins, `frame-ancestors 'none'`, `object-src 'none'`).

`'unsafe-eval'` is added to `script-src` **in development only** (`process.env.NODE_ENV === "development"`), never in production — React's dev-mode debugging tools call `eval()` for callstack reconstruction and are blocked without it (confirmed via a real browser console error); React's own message states "React will never use eval() in production mode," and the production build was verified clean without it.

### 2. CSRF — verified, not built
`lib/api/client.ts`'s double-submit CSRF token (`X-CSRF-Token` header echoing a `csrf_token` cookie on every mutating request) and the BFF proxy's cookie/header relaying (`app/api/v1/[...path]/route.ts`) were both already correctly implemented, with explicit `security.md` §6.3 references in their existing comments. No changes needed — verified compliant.

### 3. XSS / output encoding — audited, verified compliant
Grepped the entire frontend for `dangerouslySetInnerHTML`: exactly one use (`components/ui/chart.tsx`, static config only, see above). No markdown-to-HTML rendering dependency exists in `package.json`. No other raw-HTML-injection path exists anywhere in the app.

### 4. Cross-tenant denial UX audit — verified compliant, no gaps found
Checked all four resource-detail routes (`documents/[id]`, `chat/[id]`, `extractions/[id]`, `compare/[id]`) for `security.md` §3.2's "404, not 403" pattern. All four already use the identical, correct pattern: `isDoxlyApiError(error) && error.status === 404` distinguishing "doesn't exist, or you don't have access to it" (no retry offered — a 404 is a real 404) from a generic connectivity/server error (retry offered). This was built correctly and consistently across Phases 4, 9, 11, and 12 — a genuinely clean audit result, not something requiring a fix. Also verified: no `403` handling exists anywhere that could contradict this pattern, except `login-form.tsx`'s account-suspension message — which is legitimately a different concern (an account-status gate the account holder sees about their own account, not a resource-ownership check that could leak another user's data), consistent with `security.md` §3.1's own scoping of the "404 not 403" rule to resource-scoped endpoints.

### 5. Admin role guard — a real, explicitly-flagged gap, now closed
`app/(admin)/admin/layout.tsx` rendered `AdminShell` completely unguarded, with its own comment stating "Role guard (role=\"admin\", specs/security.md §3.1) is wired in Phase 2/15 alongside real session data — this layout only establishes the shell." This was a genuine, previously-deferred gap this phase's own scope names. Closed it with `AdminGuard` (`components/layout/admin-guard.tsx`), which fetches `GET /users/me` (newly added to `lib/api/users.ts`) and renders exactly one of: a loading state, a **fail-closed** "couldn't verify access" state with retry (never falls through to admin content when the role can't be confirmed), a **403-style** "you don't have permission" state for a confirmed non-admin (per `api.md`'s explicit statement that `/admin/*` is "the one place in the API where 403 is the correct code" — deliberately different copy from the 404 pattern above, since this is a role check, not a resource-ownership check), or the real `AdminShell`/children once `role === "admin"` is confirmed.

**Deliberately out of scope:** the broader "no `(dashboard)` route is gated on a session at all" question (documented in `top-bar.tsx` since Phase 2, deferred there because no backend exists yet to authenticate against and gating now would make every placeholder route unreachable in dev) is a much larger undertaking than this phase's named scope ("CSP/CSRF verification, cross-tenant denial UX audit") and is **not** addressed here — only the admin-specific role boundary, which this phase's own prior comment explicitly named as its target. Flagged as a known limitation below, not silently expanded into or silently ignored.

### 6. Pre-existing test updated to match the newly-correct behavior
`e2e/route-smoke.spec.ts`'s `/admin redirects to /admin/users` test assumed `/admin`'s redirect page always mounts and fires — true before this task, false now, because `AdminGuard` never renders `children` (and therefore never mounts the redirect) until role is confirmed, and role can never be confirmed against the real backend-less BFF. Rewrote the test to assert the guard's actual, correct, fail-closed behavior instead of the now-obsolete pre-guard assumption. This is exactly the kind of behavior change Phase 15 exists to introduce — the old test result would have meant the guard doesn't work.

## Tests
- `components/layout/admin-guard.test.tsx` — confirmed-admin renders the real shell and children; a non-admin sees the permission-denied state, never the shell; a query error fails closed (no admin content, ever).
- `e2e/route-smoke.spec.ts` (rewritten) — `/admin` shows the access-verification gate against the unreachable backend, stays on `/admin` (no redirect fires while the guard is blocking).
- Full regression: 160/160 Vitest, 55/55 Playwright (both re-run clean after every fix in this task, including the CSP nonce experiment's revert), `tsc --noEmit` clean, `eslint` clean, `next build` clean, 87/87 backend pytest, Docker Compose healthy.

## Acceptance Criteria
- Every response from the Next.js frontend carries `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Strict-Transport-Security`.
- The CSP does not break the app in production (verified: full E2E suite green against the actual production build).
- CSRF double-submit is confirmed present and correctly wired on every mutating request (verified, not modified).
- No `dangerouslySetInnerHTML` renders document- or user-derived content anywhere in the frontend (verified via full-codebase grep).
- Every resource-detail route shows a clean, non-leaking "doesn't exist, or you don't have access to it" state for a 404, never a blank page, never distinguishable from a genuine non-existence (verified across all four detail routes).
- `/admin/*` is unreachable without a confirmed `role === "admin"`, fails closed when that can't be verified, and shows a distinct 403-style message (never the 404 pattern) for a confirmed non-admin.

## Definition of Done
- [x] Code implements the Objective and satisfies all Acceptance Criteria above
- [x] Tests listed above are written and passing (160/160 Vitest, 55/55 Playwright)
- [x] No requirement silently changed or reinterpreted — the nonce-CSP investigation, its failure, and the fallback decision are fully documented (OQ-12) rather than silently choosing `'unsafe-inline'` with no record; the admin-guard gap was explicitly named in prior code comments, not discovered and silently patched without context
- [x] `specs/decisions.md` updated (OQ-12) — the one spec change this task required beyond code
- [x] Browser QA performed via mocked-network screenshots (the real backend-less BFF's live retry timing isn't reliably observable through this session's browser-automation tooling — a tab-focus/timer-throttling artifact unrelated to app correctness, worked around the same way prior phases worked around unreachable interactive states); all three `AdminGuard` states (non-admin, confirmed-admin, unreachable) verified rendering correctly
- [x] Regression check performed across Phases 1–14 (navigation, auth, documents, chat, summarization, extraction, comparison, search, analytics, forms, API interactions, shared components, responsive layouts) — no regressions found; the one required test update (`route-smoke.spec.ts`'s `/admin` test) reflects an intentional, correct behavior change this task introduced, not a regression
- [x] Basic performance review performed — `AdminGuard`'s one new query fires only on `/admin/*` routes, no impact elsewhere; security headers are static response headers with negligible overhead; no new dependencies added
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

## Known Limitations / Follow-Up (not fixed this task, scope-appropriately deferred)
- **Session gating for `(dashboard)` routes remains unimplemented.** Every non-admin dashboard route is still directly reachable without a valid session, exactly as documented since Phase 2. This is a materially larger change (real session-aware routing across the entire app) than this phase's named scope, and is not addressed here.
- **Nonce-based CSP `script-src` remains an open question (`decisions.md` OQ-12).** `'unsafe-inline'` is the working, shipped state; revisit when Next.js's Proxy-nonce support stabilizes for `output: "standalone"` + Turbopack production builds.

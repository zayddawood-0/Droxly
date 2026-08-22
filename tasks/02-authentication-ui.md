# Task P02: Authentication UI

## Task ID
P02-001..004

## Feature
Authentication — Login, Register, Password Reset, Email Verification UI

## Objective
Build the real Login, Register, Forgot Password, Reset Password, and Verify Email pages against the documented `/auth/*` contract, with client-side validation mirroring the backend's rules, a session-refresh interceptor in the API client, and functional logout — the frontend slice of `specs/roadmap.md` Phase 2 (backend auth — users/refresh_tokens tables, JWT issuance, OAuth, rate limiting — is out of scope for this task, same boundary as Phase 1's frontend-only scope).

## Specification References
- `specs/requirements.md` §1.1 (`FR-AUTH-001..008`)
- `specs/api.md` §1 (`/auth`) — the enforced request/response contract every form below is written against
- `specs/security.md` §2 (password policy, JWT/cookie/rotation, brute-force/rate-limit UX, `NFR-SEC-006` generic-error requirement)
- `specs/ui-ux.md` §2–3 (Login/Register page specs — layout, states, a11y)
- `specs/decisions.md` ADR-010 (cookie-based auth mechanism), OQ-01 (Google-only OAuth at launch, GitHub deferred)
- `skills/frontend.md` §7–9 (React Hook Form + Zod, client validation is UX-only, typed API client pattern)

## Requirements
- `FR-AUTH-001` — registration form, client-side password-policy validation, generic duplicate-email error
- `FR-AUTH-002` — `/verify-email` page auto-verifies the URL token on load
- `FR-AUTH-003` — "Continue with Google" button (full-page redirect, not a fetch call) on Login and Register
- `FR-AUTH-004` — login form, generic invalid-credentials error, account-suspended handling
- `FR-AUTH-005` — silent refresh-and-retry-once on a 401, implemented in `lib/api/client.ts`
- `FR-AUTH-006` — functional logout from the account menu
- `FR-AUTH-007` — forgot-password (always-202 UX) and reset-password (token-driven) forms
- `FR-AUTH-008` — **not in scope.** Session/device list belongs to Settings, which this plan scopes to Phase 4.

## Dependencies
- Phase 1 (Foundation) — app shell, design tokens, BFF proxy (`app/api/v1/[...path]/route.ts`), typed API client foundation (`lib/api/client.ts`). Re-verified healthy before starting this task (lint/build/18 unit tests green).

## Files Affected
- `lib/validation/auth.ts` — new — Zod schemas mirroring `api.md`'s Pydantic rules field-for-field
- `lib/api/auth.ts` — new — one function per `/auth/*` endpoint
- `lib/api/error-messages.ts` — new — shared connectivity-vs-request-error classification
- `lib/api/client.ts` — modified — refresh-and-retry-once interceptor (closes the Phase 1 TODO)
- `components/domain/auth/{password-strength-meter,google-button,form-error-banner,login-form,register-form,forgot-password-form,reset-password-form,verify-email-status}.tsx` — new
- `components/layout/top-bar.tsx` — modified — functional logout
- `components/ui/{field,alert}.tsx` — new (shadcn primitives)
- `app/(auth)/{login,register,forgot-password,reset-password,verify-email}/page.tsx` — modified — real forms replacing Phase 1 placeholders
- Tests: `lib/validation/auth.test.ts`, `lib/api/error-messages.test.ts`, component tests per form, `e2e/auth.spec.ts`

## Implementation Notes
- **No route-guarding middleware.** Gating `(dashboard)`/`(admin)` on a session now would make every existing placeholder page unreachable in dev (no backend exists to ever produce a valid session), breaking Phase 1's passing route-smoke suite. Deferred until there's a real session to gate against.
- **Account menu identity is still a placeholder.** Showing the real signed-in user needs `GET /users/me`; wiring that in is deferred to the phase that gives Dashboard real session-aware content (Phase 4), so it's built once against real data rather than twice.
- **Register's post-signup "verify your email" nudge is a toast, not the persistent Dashboard banner `ui-ux.md` §3 describes.** The persistent banner needs to know the current user's `email_verified` state, which requires the same session-awareness deferred above. Revisit when Phase 4 wires session data into the shell — `ui-ux.md` itself is not wrong here, it describes the end state; this is a sequencing choice, not a spec deviation.
- Every form is written against the real `/api/v1/auth/*` contract via the Phase 1 BFF proxy — with no backend running, requests correctly surface the proxy's real 502 (`upstream_unavailable`), rendered through the same dismissible-banner path a genuine backend outage would use. No mocked "successful login" exists anywhere in the UI code.

## Tests
- Unit — Zod schema tests (password policy boundary cases, email format), `isConnectivityError` classification
- Component — each form's validation-error, loading, and both error-class (inline vs. banner) states, using MSW to mock `/api/v1/auth/*` deterministically (`testing.md` §2.3)
- E2E — form rendering/validation across all 5 pages; a real (unmocked) request against the unreachable backend correctly shows the connectivity banner; logout redirect

## Acceptance Criteria
- Given a valid, unused email and compliant password, submitting Register calls `POST /auth/register` with the correct payload shape.
- Given a weak password, Register blocks submission client-side with a field-level error, before any request fires.
- Given a 401 from `POST /auth/login`, Login shows the single generic "Invalid email or password" message, never a field-specific one.
- Given any endpoint returns 401 mid-session (not `/auth/login` or `/auth/refresh` itself), the client calls `POST /auth/refresh` once and retries the original request before surfacing an error.
- Given the backend is unreachable, every form shows the dismissible connectivity banner, never a raw exception or blank failure.
- Logout calls `POST /auth/logout` and redirects to `/login` on success.

## Definition of Done
- [x] Code implements the Objective and satisfies the Acceptance Criteria
- [x] Tests listed above are written and passing
- [x] No requirement silently changed or reinterpreted — the two scope boundaries above (route-guarding, persistent verification banner) are documented here, not improvised silently
- [x] No spec file required a content change this task (no API contract, requirement, or design-system change was needed — `api.md`, `ui-ux.md`, `requirements.md` already matched what was built)
- [ ] Linked in a PR description with phase (Phase 2) — pending actual PR creation (no git repo yet)

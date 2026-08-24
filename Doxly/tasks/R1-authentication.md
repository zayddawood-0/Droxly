# Task R1: Authentication Remediation

## Task ID
R1-001

## Feature
Authentication — full backend implementation: registration, login, JWT access/refresh, logout, password reset, email verification, Google OAuth, session management, profile/usage, plus the shared security infrastructure every later remediation task depends on (CSRF, rate limiting, `require_admin`).

## Objective
Close the router/service integration gap identified by the API Router Gap Audit and formalized in `tasks/remediation-plan.md` R1: `User`/`RefreshToken` models and schema-level repository methods existed, but no password hashing, JWT issuance, OAuth, CSRF protection, rate limiting, or HTTP layer existed anywhere. This task builds all of it, establishing the `user_id` identity every subsequent remediation task (R2–R10) depends on.

## Specification References
- `tasks/remediation-plan.md` §4 (R1, Revision 2) — the authoritative scope for this task, including §4.1 (CSRF), §4.2 (rate limiting), §4.3 (`require_admin`).
- `specs/requirements.md` §1.1 (`FR-AUTH-001..008`), §1.2 (`FR-USER-001`, `FR-USER-003`).
- `specs/api.md` §0.3–0.7 (conventions), §1 (`/auth`), §2 (`/users`).
- `specs/security.md` §2 (Authentication Security), §3.1 (role model), §6.3 (CSRF), full file for the brute-force/rate-limit/cookie conventions.
- `specs/decisions.md` ADR-010 (JWT/OAuth mechanism).
- `specs/database.md` §3.1–3.2 (`users`, `refresh_tokens`).
- `specs/observability.md` §1 (Never-Log List), §9 (audit logs).
- `skills/backend.md` (full — layering, DI, error handling, folder structure).
- `specs/testing.md` §3.4 (Authentication tests), §3.5 (cross-tenant, mandatory category).

## Requirements
- `FR-AUTH-001` (P0) — registration.
- `FR-AUTH-002` (P1) — email verification.
- `FR-AUTH-003` (P0) — Google OAuth.
- `FR-AUTH-004` (P0) — login.
- `FR-AUTH-005` (P0) — session refresh.
- `FR-AUTH-006` (P0) — logout.
- `FR-AUTH-007` (P0) — password reset.
- `FR-AUTH-008` (P1) — session/device management.
- `FR-USER-001` (P0) — view/edit profile.
- `FR-USER-003` (P1) — view plan & usage.
- `NFR-SEC-001` — multi-tenancy (identity establishment for every later task).
- `NFR-SEC-002` — brute-force/rate-limit protection.
- `NFR-SEC-010` — CSRF protection.
- `NFR-SEC-006` — non-enumerating error messages.
- `NFR-SEC-009` — sanitized error responses.

## Dependencies
- Phase 3 (Database) — `users`/`refresh_tokens` schema already exists.
- None outstanding — R1 is the first remediation task, with no upstream R-task dependency.

## Files Affected
See the Final Report for the complete, verified list produced by this task's actual implementation.

## Implementation Notes
Follows `skills/backend.md`'s layering exactly: `api/v1/routers/{auth,users}.py` → `services/{auth_service,user_service}.py` → `repositories/user_repository.py` (extended) → DB. Shared security infrastructure (`core/security.py`, `core/csrf.py`, `core/rate_limit.py`, `core/dependencies.py`) is built once in R1 for reuse by every later router. Password hashing: argon2 (argon2-cffi, argon2id). Access tokens: PyJWT, HS256, 15 min, claims limited to `sub`/`role`/`iat`/`exp`. Refresh tokens: opaque `secrets.token_urlsafe`, SHA-256 hash persisted, rotated on every use, family-reuse detection revokes all sessions. CSRF: FastAPI issues the `csrf_token` cookie (frontend already relays it transparently — verified, zero frontend change needed). Rate limiting: Redis token-bucket, general (60/min) + AI (10/min + daily cap) + auth-specific (account+IP) tiers. Email: new `EmailProvider` abstraction (Fake default, SMTP real implementation, stdlib-only) mirroring the existing `LLMProvider`/`EmbeddingProvider` pattern — documented as `decisions.md` ADR-020. OAuth: Authlib `AsyncOAuth2Client`, state-CSRF cookie pattern, graceful `oauth_not_configured` response when `GOOGLE_OAUTH_CLIENT_ID`/`SECRET` are unset (true in this environment — noted as an untestable-without-real-credentials integration point, same honesty standard applied throughout this remediation effort).

## Tests
- `testing.md` §3.4 — full `FR-AUTH-001..008` suite.
- `testing.md` §3.5 — cross-tenant (from `GET /users/me` onward).
- New: CSRF suite (§4.1), rate-limit suite (§4.2), `require_admin` unit test (§4.3).
- Service-layer unit tests (repositories faked, per `skills/backend.md` §3).

## Acceptance Criteria
Copied from `specs/requirements.md` §1.1–1.2 verbatim per requirement ID above — see the Final Report for pass/fail status against each.

## Definition of Done
- [ ] Code implements the Objective and satisfies all Acceptance Criteria
- [ ] Tests listed above are written and passing
- [ ] No requirement silently changed or reinterpreted
- [ ] `specs/decisions.md` updated (ADR-020, EmailProvider + Redis-unavailable fail-mode decision)
- [ ] Linked in the PR description with the requirement IDs and phase — pending PR creation (not requested this session)

"""
tasks/remediation-plan.md R1 — get_current_user, get_db_session, and
require_admin (skills/backend.md §15's folder plan; §4.3 of the remediation
plan corrects Revision 1's omission of require_admin from this file).
"""

from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import AccessTokenClaims, InvalidTokenError, decode_access_token
from app.errors import AccountSuspendedError, ForbiddenError, UnauthorizedError
from app.repositories.user_repository import UserRepository

# Re-exported (not re-implemented) from core/database.py so every router/
# service imports session provisioning from the same `app.core.dependencies`
# module as get_current_user/require_admin, per skills/backend.md §15's
# folder plan. **Fixed during R1's compliance-remediation pass**: this used
# to be a *wrapping* generator (`async for session in _get_db_session():
# yield session`) around the real one — which looks equivalent but silently
# breaks exception propagation. FastAPI throws a raised exception into a
# yield-based dependency via `.athrow()` at that dependency's own `yield`
# point; when the `yield` lives inside a wrapper's `async for` loop (not
# inside the real generator itself), the exception surfaces at the
# *wrapper's* yield and never reaches the inner generator's try/except at
# all — so core/database.py's commit-on-DoxlyError / rollback-on-error
# logic (this same remediation pass, S7-adjacent) never ran, silently
# discarding the audit_logs row S7 added. Confirmed live: a real server run
# showed zero audit_logs rows for a failed login even after that fix, and
# only stopped being empty once the double-wrapping was removed here — a
# straight re-export doesn't have this problem, since it's the exact same
# function object/generator FastAPI resolves and drives directly.
__all__ = [
    "get_current_user",
    "get_current_user_optional",
    "get_db_session",
    "require_admin",
]

ACCESS_TOKEN_COOKIE_NAME = "access_token"


def _decode_cookie(access_token: str | None) -> AccessTokenClaims | None:
    if not access_token:
        return None
    try:
        return decode_access_token(access_token)
    except InvalidTokenError:
        return None


async def get_current_user(
    access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_db_session),
) -> AccessTokenClaims:
    """
    skills/backend.md §8 — the only path by which a router learns who is
    calling. Verifies the JWT from the httpOnly access_token cookie
    (decisions.md ADR-010) and extracts user_id from its verified claims —
    never from a client-supplied body/query field. Raises 401 for a
    missing/expired/invalid token (api.md §0.4) — see
    get_current_user_optional below for the one case (pre-session rate
    limiting) that needs a non-raising variant.

    R10 (tasks/remediation-plan.md, FR-ADMIN-003) — added a live
    `users.status` check here, on every authenticated request, not just at
    login/refresh (auth_service.py already checked it at both of those
    points, mirrored here). Without this, `POST /admin/users/{id}/suspend`
    could only ever block a *future* login/refresh — an already-issued,
    still-unexpired access token (~15 min, decisions.md ADR-010) would keep
    working right through it, silently under-implementing the requirement's
    own explicit "immediately revoking all sessions" wording. The
    trade-off (one extra indexed lookup per authenticated request,
    app-wide) was confirmed deliberately rather than assumed — a fully
    stateless-JWT alternative (a token denylist/version claim) was
    available but not chosen, since it would have meant new stored state
    for a mechanism the DB already models via `users.status`.
    """
    claims = _decode_cookie(access_token)
    if claims is None:
        raise UnauthorizedError()
    user = await UserRepository(db).get_by_id(claims.user_id)
    if user is None:
        raise UnauthorizedError()
    if user.status == "suspended":
        raise AccountSuspendedError()
    return claims


async def get_current_user_optional(
    access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
) -> AccessTokenClaims | None:
    """
    Non-raising variant used only where an endpoint is legitimately called
    both authenticated and unauthenticated (core/rate_limit.py's general
    tier, which api.md §0.7 applies "to every endpoint by default" including
    the pre-session auth endpoints that have no user yet) — every other
    dependency in this codebase should use get_current_user, not this one.
    """
    return _decode_cookie(access_token)


async def require_admin(
    current_user: AccessTokenClaims = Depends(get_current_user),
) -> AccessTokenClaims:
    """
    security.md §3.1's role check: "does the caller's role permit this
    endpoint at all." Composes get_current_user (never re-implements JWT
    verification) and additionally checks role=='admin'. A valid,
    non-admin token gets 403 (api.md §0.4 — 403 is reserved for role
    checks, never tenant-ownership checks); no token at all still surfaces
    as 401 via get_current_user itself.

    Built in R1 with no consumer yet — R10 (Admin Integration) is the first
    and only router that declares this as a route dependency
    (tasks/remediation-plan.md R1 §4.3). Never a substitute for the
    ownership-scoped repository calls resource-scoped endpoints still use —
    the admin role is never a bypass of tenant isolation.
    """
    if current_user.role != "admin":
        raise ForbiddenError("This action requires an administrator role.")
    return current_user

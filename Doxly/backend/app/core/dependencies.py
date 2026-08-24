"""
tasks/remediation-plan.md R1 — get_current_user, get_db_session, and
require_admin (skills/backend.md §15's folder plan; §4.3 of the remediation
plan corrects Revision 1's omission of require_admin from this file).
"""

from collections.abc import AsyncIterator

from fastapi import Cookie, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session as _get_db_session
from app.core.security import AccessTokenClaims, InvalidTokenError, decode_access_token
from app.errors import ForbiddenError, UnauthorizedError

ACCESS_TOKEN_COOKIE_NAME = "access_token"


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Re-exported from core/database.py so every router/service imports
    session provisioning from the same `app.core.dependencies` module as
    get_current_user/require_admin, per skills/backend.md §15's folder plan
    — core/database.py's own docstring already anticipated this."""
    async for session in _get_db_session():
        yield session


def _decode_cookie(access_token: str | None) -> AccessTokenClaims | None:
    if not access_token:
        return None
    try:
        return decode_access_token(access_token)
    except InvalidTokenError:
        return None


async def get_current_user(
    access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
) -> AccessTokenClaims:
    """
    skills/backend.md §8 — the only path by which a router learns who is
    calling. Verifies the JWT from the httpOnly access_token cookie
    (decisions.md ADR-010) and extracts user_id from its verified claims —
    never from a client-supplied body/query field. Raises 401 for a
    missing/expired/invalid token (api.md §0.4) — see
    get_current_user_optional below for the one case (pre-session rate
    limiting) that needs a non-raising variant.
    """
    claims = _decode_cookie(access_token)
    if claims is None:
        raise UnauthorizedError()
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

"""
tasks/remediation-plan.md R1 §4.1 — CSRF double-submit protection
(NFR-SEC-010, security.md §6.3).

Division of responsibility (resolved during this task, not assumed):
frontend/lib/api/client.ts already reads a `csrf_token` cookie and sends it
as `X-CSRF-Token` on every mutating request — verified by reading that file
directly, zero frontend change needed. frontend/app/api/v1/[...path]/route.ts
already forwards both the `cookie` header and `x-csrf-token` header
untouched in both directions. FastAPI is therefore the actual origin of the
`csrf_token` cookie value (set alongside the access/refresh cookies at
login/register/OAuth success) and the sole verifier — this module is that
issuance/verification logic.
"""

import secrets

from fastapi import Request, Response

from app.core.config import settings
from app.errors import CsrfError

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"

# Methods that mutate state per api.md §6.3 — GET/HEAD/OPTIONS never carry a
# body that changes anything, so they're exempt (matches SameSite=Lax's own
# "safe methods" distinction).
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    """
    Deliberately NOT httponly — security.md §6.3 requires the frontend's own
    JavaScript to read this cookie and echo it as a header; that's the
    entire double-submit mechanism (an attacker's cross-site page can trigger
    a request carrying the cookie, but same-origin-policy stops it from
    *reading* the cookie value to also set the matching header).
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=settings.environment != "local",
        samesite="lax",
        max_age=60 * 60 * 24 * 30,  # matches the refresh-token session lifetime
    )


async def verify_csrf(request: Request) -> None:
    """
    Router-level dependency (applied once per router, not once per route) —
    self-skips safe methods so it can be declared on an APIRouter's
    `dependencies=[Depends(verify_csrf)]` without needing every individual
    mutating route to remember it separately. Exempt endpoints (register/
    login/refresh/oauth start+callback/password-reset request+confirm/
    verify-email — api.md §0.3's pre-session list) never issue a CSRF cookie
    in the first place, so they're excluded at the router-mounting level in
    main.py, not here.
    """
    if request.method not in _MUTATING_METHODS:
        return

    header_token = request.headers.get(CSRF_HEADER_NAME)
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)

    if (
        not header_token
        or not cookie_token
        or not secrets.compare_digest(header_token, cookie_token)
    ):
        raise CsrfError()

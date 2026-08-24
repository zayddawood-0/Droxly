"""
tasks/remediation-plan.md R1 — password hashing, JWT access-token
issuance/verification, opaque refresh-token generation/hashing, and the
Google OAuth2 client. Mechanism decided by decisions.md ADR-010; hardening
detail (algorithm choice, claim set, rotation) by security.md §2.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from authlib.integrations.httpx_client import AsyncOAuth2Client

from app.core.config import settings

# security.md §2.1 — argon2id (the library's default profile), a per-hash
# random salt embedded by argon2 itself, no separate salt column needed.
_password_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Never raises on a wrong password — returns False, matching the
    generic invalid_credentials error path (NFR-SEC-006)."""
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


@dataclass
class AccessTokenClaims:
    user_id: uuid.UUID
    role: str


class InvalidTokenError(Exception):
    """Raised for any access-token verification failure — expired, malformed, bad signature."""


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    """
    security.md §2.2 — claims limited to sub/role/iat/exp; no email, no PII.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token, settings.jwt_signing_key, algorithms=[JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]), role=payload["role"]
        )
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("malformed token claims") from exc


def generate_refresh_token() -> str:
    """
    security.md §2.2 — opaque random value, not a JWT, so it carries no
    client-decodable claims. The raw value is what's set in the cookie;
    only its hash is ever persisted (hash_refresh_token below).
    """
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    """
    SHA-256 is sufficient (not argon2) for a high-entropy random token being
    hashed for lookup-by-equality, not a low-entropy human password being
    hashed against brute-force guessing — the same distinction security.md
    draws between password_hash (argon2) and refresh_tokens.token_hash.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def parse_device_label(user_agent: str | None) -> str | None:
    """
    security.md §2.5 — "device_label populated from User-Agent parsing at
    issuance." A minimal heuristic, not a full UA-parsing dependency
    (CLAUDE.md §5 — no unnecessary dependency for a display-only label):
    recognizes the handful of browser/OS tokens actually useful to a user
    scanning their own session list, falls back to a generic label rather
    than failing or storing the raw (potentially long, low-signal) string.
    """
    if not user_agent:
        return None

    browser = next(
        (
            name
            for name in ("Edg", "Chrome", "Firefox", "Safari", "OPR")
            if name in user_agent
        ),
        "Unknown browser",
    )
    browser = {"Edg": "Edge", "OPR": "Opera"}.get(browser, browser)

    os_name = next(
        (
            name
            for name in ("Windows", "Macintosh", "Linux", "Android", "iPhone", "iPad")
            if name in user_agent
        ),
        "Unknown OS",
    )
    os_label = {"Macintosh": "macOS", "iPhone": "iOS", "iPad": "iPadOS"}.get(
        os_name, os_name
    )

    return f"{browser} on {os_label}"


def create_action_token(
    user_id: uuid.UUID, *, purpose: str, expires_in: timedelta
) -> str:
    """
    Email-verification (FR-AUTH-002) and password-reset (FR-AUTH-007)
    tokens. Deliberately stateless (a signed JWT, not a row in a new
    table): `database.md` defines no email-verification/password-reset
    token table, and neither FR-AUTH-002's nor FR-AUTH-007's acceptance
    criteria require single-use invalidation before natural expiry — both
    are satisfied by "valid, unexpired, correct purpose" alone. Adding a
    new migration for this was judged out of R1's necessary scope; this
    tradeoff (a reset/verify link remains valid, if re-visited, for its
    full window rather than being burned on first use) is a deliberate,
    documented design choice, not an oversight.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "purpose": purpose,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=JWT_ALGORITHM)


def decode_action_token(token: str, *, expected_purpose: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token, settings.jwt_signing_key, algorithms=[JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("purpose") != expected_purpose:
        raise InvalidTokenError("token purpose mismatch")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("malformed token claims") from exc


def google_oauth_client() -> AsyncOAuth2Client | None:
    """
    None when GOOGLE_OAUTH_CLIENT_ID/SECRET aren't configured (true in every
    environment this remediation task was implemented/tested in) — callers
    must handle None by returning oauth_not_configured rather than crashing
    (ai.md's "handle provider failures gracefully" principle, applied here
    to a configuration failure rather than a runtime one).
    """
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        return None
    return AsyncOAuth2Client(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scope="openid email profile",
    )


GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

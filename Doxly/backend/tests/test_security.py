import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_action_token,
    decode_access_token,
    decode_action_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    parse_device_label,
    verify_password,
)


def test_password_hash_round_trip():
    hashed = hash_password("correct-horse-9")
    assert verify_password("correct-horse-9", hashed) is True


def test_password_verify_wrong_password_returns_false_not_raises():
    hashed = hash_password("correct-horse-9")
    assert verify_password("wrong-password-1", hashed) is False


def test_access_token_round_trip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "user")
    claims = decode_access_token(token)
    assert claims.user_id == user_id
    assert claims.role == "user"


def test_access_token_claims_are_minimal():
    """security.md §2.2 — claims limited to sub/role/iat/exp, no PII."""
    token = create_access_token(uuid.uuid4(), "admin")
    payload = jwt.decode(token, options={"verify_signature": False})
    assert set(payload.keys()) == {"sub", "role", "iat", "exp"}


def test_access_token_tampered_signature_rejected():
    token = create_access_token(uuid.uuid4(), "user")
    tampered = token[:-4] + "abcd"
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_access_token_expired_rejected():
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "user",
        "iat": jwt.api_jwt.datetime.now(jwt.api_jwt.timezone.utc) - timedelta(hours=1),
        "exp": jwt.api_jwt.datetime.now(jwt.api_jwt.timezone.utc)
        - timedelta(minutes=1),
    }
    from app.core.config import settings
    from app.core.security import JWT_ALGORITHM

    expired = jwt.encode(payload, settings.jwt_signing_key, algorithm=JWT_ALGORITHM)
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired)


def test_refresh_token_is_opaque_and_hash_is_deterministic():
    raw = generate_refresh_token()
    assert len(raw) > 20
    assert hash_refresh_token(raw) == hash_refresh_token(raw)
    assert hash_refresh_token(raw) != raw


def test_refresh_token_hash_differs_for_different_tokens():
    assert hash_refresh_token(generate_refresh_token()) != hash_refresh_token(
        generate_refresh_token()
    )


def test_action_token_round_trip():
    user_id = uuid.uuid4()
    token = create_action_token(
        user_id, purpose="verify_email", expires_in=timedelta(hours=1)
    )
    assert decode_action_token(token, expected_purpose="verify_email") == user_id


def test_action_token_wrong_purpose_rejected():
    """A password-reset token must not verify an email, and vice versa."""
    token = create_action_token(
        uuid.uuid4(), purpose="password_reset", expires_in=timedelta(hours=1)
    )
    with pytest.raises(InvalidTokenError):
        decode_action_token(token, expected_purpose="verify_email")


def test_action_token_expired_rejected():
    token = create_action_token(
        uuid.uuid4(), purpose="verify_email", expires_in=timedelta(seconds=-1)
    )
    with pytest.raises(InvalidTokenError):
        decode_action_token(token, expected_purpose="verify_email")


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        (None, None),
        ("", None),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            "Chrome on Windows",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
            "Safari on macOS",
        ),
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1", "Safari on iOS"),
    ],
)
def test_parse_device_label(user_agent, expected):
    assert parse_device_label(user_agent) == expected

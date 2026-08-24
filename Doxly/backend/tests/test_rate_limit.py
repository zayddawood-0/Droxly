"""
tasks/remediation-plan.md R1 §4.2 — dedicated rate-limit suite against the
real Redis instance (docker-compose.yml's `redis` service). Uses small,
test-local capacity/period values (never the real 60/min or 10/min
constants) so each test runs in milliseconds instead of minutes, and a
fresh UUID-suffixed key per test so tests never share bucket state.
"""

import uuid

import pytest

from app.core.rate_limit import _check_token_bucket, auth_throttle
from app.errors import RateLimitedError


def _fresh_key(prefix: str) -> str:
    return f"test:{prefix}:{uuid.uuid4()}"


async def test_token_bucket_allows_up_to_capacity():
    key = _fresh_key("bucket")
    for _ in range(3):
        result = await _check_token_bucket(key, capacity=3, period_seconds=60)
        assert result.allowed is True


async def test_token_bucket_rejects_once_exhausted():
    key = _fresh_key("bucket")
    for _ in range(3):
        await _check_token_bucket(key, capacity=3, period_seconds=60)

    result = await _check_token_bucket(key, capacity=3, period_seconds=60)
    assert result.allowed is False
    assert result.retry_after_seconds > 0


async def test_token_bucket_refills_over_time():
    import asyncio

    key = _fresh_key("bucket")
    # capacity=1 over a 1-second period refills fully within ~1s.
    first = await _check_token_bucket(key, capacity=1, period_seconds=1)
    assert first.allowed is True

    immediately_after = await _check_token_bucket(key, capacity=1, period_seconds=1)
    assert immediately_after.allowed is False

    await asyncio.sleep(1.1)
    refilled = await _check_token_bucket(key, capacity=1, period_seconds=1)
    assert refilled.allowed is True


async def test_token_bucket_keys_are_independent():
    """Two different keys never share a bucket — the isolation property the
    per-user/per-IP keying in rate_limit_general/rate_limit_ai depends on."""
    key_a, key_b = _fresh_key("a"), _fresh_key("b")
    await _check_token_bucket(key_a, capacity=1, period_seconds=60)

    result_b = await _check_token_bucket(key_b, capacity=1, period_seconds=60)
    assert result_b.allowed is True


async def test_auth_throttle_allows_under_threshold():
    identifier, ip = str(uuid.uuid4()), "203.0.113.1"
    for _ in range(4):
        await auth_throttle.record_failure(identifier, ip)
    # 4 failures < THRESHOLD(5) — check() must not raise.
    await auth_throttle.check(identifier, ip)


async def test_auth_throttle_blocks_at_threshold():
    identifier, ip = str(uuid.uuid4()), "203.0.113.2"
    for _ in range(5):
        await auth_throttle.record_failure(identifier, ip)

    with pytest.raises(RateLimitedError):
        await auth_throttle.check(identifier, ip)


async def test_auth_throttle_keyed_by_account_and_ip_together():
    """security.md §2.4 — the same account from a DIFFERENT IP is not
    throttled by another IP's failures against it (and vice versa)."""
    identifier = str(uuid.uuid4())
    for _ in range(5):
        await auth_throttle.record_failure(identifier, "203.0.113.3")

    # A different IP against the same account is a fresh bucket.
    await auth_throttle.check(identifier, "203.0.113.4")


async def test_auth_throttle_reset_clears_the_counter():
    identifier, ip = str(uuid.uuid4()), "203.0.113.5"
    for _ in range(5):
        await auth_throttle.record_failure(identifier, ip)

    await auth_throttle.reset(identifier, ip)
    await auth_throttle.check(identifier, ip)  # must not raise

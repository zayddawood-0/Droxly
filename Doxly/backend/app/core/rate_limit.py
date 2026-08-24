"""
tasks/remediation-plan.md R1 §4.2 — Redis-backed rate limiting
(api.md §0.7, security.md §2.4, NFR-SEC-002). Two independent mechanisms,
matching the two distinct behaviors the specs describe:

1. TokenBucket — smooth per-minute/per-day request-volume limiting (the
   general 60/min tier and the AI 10/min + daily-cap tier), applied on
   every request regardless of outcome.
2. AuthThrottle — progressive-backoff brute-force protection keyed by
   account+IP (security.md §2.4), which counts *failed* login attempts
   specifically, not raw request volume — a different shape of problem
   from #1, so it is not built as a third TokenBucket tier.

Redis-unavailable failure mode: **fails open** (allows the request, logs a
warning) rather than failing closed. Flagged in the remediation plan as an
open decision this task had to make; documented as decisions.md ADR-020 —
an outage of the rate limiter itself should degrade to "no rate limiting"
rather than take the whole API down, matching NFR-AVAIL-001's "core
functionality remains available even if a supporting subsystem is degraded"
principle applied here to Redis rather than the AI subsystem.
"""

import logging
import time
import uuid
from dataclasses import dataclass

import redis.asyncio as redis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import (
    get_current_user,
    get_current_user_optional,
    get_db_session,
)
from app.core.security import AccessTokenClaims
from app.errors import DailyAiLimitExceededError, RateLimitedError
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

redis_client: redis.Redis = redis.from_url(settings.redis_url, decode_responses=True)

# Atomic token-bucket refill+consume, per bucket key. KEYS[1]=bucket key,
# ARGV: capacity, refill_period_seconds, now, cost(=1). Returns
# {allowed(0/1), retry_after_seconds}. Run server-side via EVAL so a race
# between concurrent requests for the same key can't both read stale token
# counts and both be admitted (the correctness property a rate limiter
# actually depends on under concurrent load).
_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local period = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call("HMGET", key, "tokens", "ts")
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

local elapsed = math.max(0, now - ts)
local refill_rate = capacity / period
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
local retry_after = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry_after = math.ceil((1 - tokens) / refill_rate)
end

redis.call("HMSET", key, "tokens", tokens, "ts", now)
redis.call("EXPIRE", key, period * 2)

return {allowed, retry_after}
"""

_token_bucket_script = redis_client.register_script(_TOKEN_BUCKET_SCRIPT)


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


async def _check_token_bucket(
    key: str, *, capacity: int, period_seconds: int
) -> RateLimitResult:
    try:
        allowed, retry_after = await _token_bucket_script(
            keys=[key], args=[capacity, period_seconds, time.time()]
        )
    except redis.RedisError:
        logger.warning(
            "rate_limit.redis_unavailable", extra={"key_prefix": key.split(":")[0]}
        )
        return RateLimitResult(allowed=True, retry_after_seconds=0)
    return RateLimitResult(allowed=bool(allowed), retry_after_seconds=int(retry_after))


GENERAL_TIER_CAPACITY = 60
GENERAL_TIER_PERIOD_SECONDS = 60
AI_TIER_CAPACITY = 10
AI_TIER_PERIOD_SECONDS = 60
AI_DAILY_CAP_FREE = 30
AI_DAILY_CAP_PRO = 500


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def rate_limit_general(
    request: Request,
    current_user: AccessTokenClaims | None = Depends(get_current_user_optional),
) -> None:
    """
    api.md §0.7 — 60 req/min, "applies to every endpoint below by default."
    Keyed by user_id once authenticated; falls back to client IP for the
    pre-session auth endpoints, which still need *a* general-tier key even
    though they have no user_id yet (their stricter, failure-aware
    protection is the separate AuthThrottle below, layered on top).
    """
    key = (
        f"rl:general:{current_user.user_id}"
        if current_user
        else f"rl:general:ip:{_client_ip(request)}"
    )
    result = await _check_token_bucket(
        key, capacity=GENERAL_TIER_CAPACITY, period_seconds=GENERAL_TIER_PERIOD_SECONDS
    )
    if not result.allowed:
        raise RateLimitedError(result.retry_after_seconds)


async def _require_user_and_plan(
    current_user: AccessTokenClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> tuple[uuid.UUID, str]:
    """
    get_current_user's JWT claims deliberately don't carry `plan`
    (security.md §2.2 limits access-token claims to sub/role/iat/exp) — the
    AI daily-cap tier is the one place that needs it, so it's looked up
    here via the standard DI-provided session rather than widening the JWT
    claim set for every request just for this one route family.
    """
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(current_user.user_id)
    plan = user.plan if user else "free"
    return current_user.user_id, plan


async def rate_limit_ai(
    identity: tuple[uuid.UUID, str] = Depends(_require_user_and_plan),
) -> None:
    """
    api.md §0.7 — the stricter AI-invoking tier: 10/min plus a daily cap
    (Free: 30/day, Pro: 500/day). Applied only to the five routes api.md
    names explicitly (chat messages, summaries, extractions, comparisons,
    reprocess) — each of R2/R4/R5/R6/R7's routers depends on this
    function directly on that one route, not router-wide like the general
    tier or CSRF.
    """
    user_id, plan = identity

    per_minute = await _check_token_bucket(
        f"rl:ai:{user_id}",
        capacity=AI_TIER_CAPACITY,
        period_seconds=AI_TIER_PERIOD_SECONDS,
    )
    if not per_minute.allowed:
        raise RateLimitedError(per_minute.retry_after_seconds)

    daily_cap = AI_DAILY_CAP_PRO if plan == "pro" else AI_DAILY_CAP_FREE
    seconds_until_midnight_utc = 86400 - int(time.time()) % 86400
    daily = await _check_token_bucket(
        f"rl:ai_daily:{user_id}", capacity=daily_cap, period_seconds=86400
    )
    if not daily.allowed:
        raise DailyAiLimitExceededError(seconds_until_midnight_utc)


class AuthThrottle:
    """
    security.md §2.4 — progressive backoff after 5 failures in a 10-minute
    window, keyed by account+IP (never the account alone, so a legitimate
    user isn't punished for someone else's attempts against their email from
    a different IP — and never the IP alone, so an attacker can't spray many
    accounts from one IP to dodge a per-account limit).
    """

    WINDOW_SECONDS = 600
    THRESHOLD = 5

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def _key(self, identifier: str, ip: str) -> str:
        return f"rl:auth_throttle:{identifier}:{ip}"

    async def check(self, identifier: str, ip: str) -> None:
        try:
            raw_count = await self._client.get(self._key(identifier, ip))
        except redis.RedisError:
            logger.warning(
                "rate_limit.redis_unavailable", extra={"key_prefix": "auth_throttle"}
            )
            return
        count = int(raw_count) if raw_count else 0
        if count >= self.THRESHOLD:
            # Progressive backoff: doubles per attempt past the threshold,
            # capped at the window itself so a very old streak doesn't
            # imply an absurd wait time.
            delay = min(2 ** (count - self.THRESHOLD + 1), self.WINDOW_SECONDS)
            raise RateLimitedError(
                delay, message="Too many attempts. Please wait before trying again."
            )

    async def record_failure(self, identifier: str, ip: str) -> None:
        try:
            key = self._key(identifier, ip)
            new_count = await self._client.incr(key)
            if new_count == 1:
                await self._client.expire(key, self.WINDOW_SECONDS)
        except redis.RedisError:
            logger.warning(
                "rate_limit.redis_unavailable", extra={"key_prefix": "auth_throttle"}
            )

    async def reset(self, identifier: str, ip: str) -> None:
        try:
            await self._client.delete(self._key(identifier, ip))
        except redis.RedisError:
            logger.warning(
                "rate_limit.redis_unavailable", extra={"key_prefix": "auth_throttle"}
            )


auth_throttle = AuthThrottle(redis_client)

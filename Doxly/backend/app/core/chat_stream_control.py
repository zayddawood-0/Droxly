"""
tasks/remediation-plan.md R4 — decisions.md ADR-024: a Redis-backed signal
for `POST .../messages/{id}/stop` (`FR-AI-006`, `api.md` §4) to reach an
in-flight streaming turn that may be running on a *different* API replica
than the one handling the `/stop` request (`NFR-SCALE-001` — stateless,
horizontally-scalable API containers rule out a plain in-process registry).

Keyed by the **user** message's id — per `frontend/hooks/use-chat-stream.ts`
(already built, verified by direct inspection): the client only ever knows
the user message's id at the moment a user clicks "stop" (captured from the
`event: message_id` SSE event, sent first); the assistant message for that
turn has no id yet from the client's perspective, since it isn't persisted
until the turn ends. `/stop`'s `{message_id}` path parameter is therefore
the user message's id, not an (as-yet-nonexistent) assistant message id.
"""

import logging

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_TURN_TTL_SECONDS = 300  # generous upper bound on how long one turn can run

redis_client: redis.Redis = redis.from_url(settings.redis_url, decode_responses=True)


def _key(user_message_id: object) -> str:
    return f"chat_turn:{user_message_id}"


async def mark_turn_started(user_message_id: object) -> None:
    """Called once, right before generation begins, so a /stop request has
    something to find. Fails open (decisions.md ADR-021/023 precedent) — a
    Redis outage here just means /stop won't find this turn later (409),
    not that generation itself fails."""
    try:
        await redis_client.set(_key(user_message_id), "running", ex=_TURN_TTL_SECONDS)
    except redis.RedisError:
        logger.warning(
            "chat_stream_control.redis_unavailable",
            extra={"phase": "mark_started"},
        )


async def mark_turn_finished(user_message_id: object) -> None:
    """Called once the turn reaches any terminal outcome (done/stopped/error) — frees the key immediately rather than waiting out the TTL."""
    try:
        await redis_client.delete(_key(user_message_id))
    except redis.RedisError:
        logger.warning(
            "chat_stream_control.redis_unavailable",
            extra={"phase": "mark_finished"},
        )


async def request_stop(user_message_id: object) -> bool:
    """
    Returns True if a running turn was found and flagged (the caller
    returns 200), False if there was nothing in progress to stop (the
    caller returns `409 not_in_progress`, api.md §4).
    """
    try:
        current = await redis_client.get(_key(user_message_id))
        if current != "running":
            return False
        await redis_client.set(
            _key(user_message_id), "stop_requested", ex=_TURN_TTL_SECONDS
        )
        return True
    except redis.RedisError:
        logger.warning(
            "chat_stream_control.redis_unavailable",
            extra={"phase": "request_stop"},
        )
        # Fail open toward "let generation continue" rather than falsely
        # reporting a stop was accepted when nothing can act on it.
        return False


async def is_stop_requested(user_message_id: object) -> bool:
    try:
        return await redis_client.get(_key(user_message_id)) == "stop_requested"
    except redis.RedisError:
        return False

"""Redis-backed session manager with 30-minute TTL."""

from __future__ import annotations

import json
import logging
import os
import uuid

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SESSION_TTL = 1800  # 30 minutes
SESSION_PREFIX = "hedge:session:"

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def get_or_create_session(session_id: str | None) -> tuple[str, list[dict]]:
    """Get existing session or create a new one. Returns (session_id, messages)."""
    r = _get_redis()

    if session_id:
        raw = r.get(f"{SESSION_PREFIX}{session_id}")
        if raw:
            data = json.loads(raw)
            r.expire(f"{SESSION_PREFIX}{session_id}", SESSION_TTL)
            return session_id, data.get("messages", [])

    # Create new session
    new_id = str(uuid.uuid4())
    _save_session(new_id, [])
    return new_id, []


def update_session(session_id: str, messages: list[dict], context: dict | None = None):
    """Update session with new messages and optional context."""
    r = _get_redis()
    data = {"messages": messages}
    if context:
        data["context"] = context
    r.setex(
        f"{SESSION_PREFIX}{session_id}",
        SESSION_TTL,
        json.dumps(data),
    )


def get_session(session_id: str) -> dict | None:
    """Get session data."""
    r = _get_redis()
    raw = r.get(f"{SESSION_PREFIX}{session_id}")
    if raw:
        return json.loads(raw)
    return None


def delete_session(session_id: str) -> bool:
    """Delete a session."""
    r = _get_redis()
    return bool(r.delete(f"{SESSION_PREFIX}{session_id}"))


def _save_session(session_id: str, messages: list[dict]):
    r = _get_redis()
    r.setex(
        f"{SESSION_PREFIX}{session_id}",
        SESSION_TTL,
        json.dumps({"messages": messages}),
    )

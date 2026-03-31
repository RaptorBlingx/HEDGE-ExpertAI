"""Metadata Ingest — FastAPI routes."""

from __future__ import annotations

import logging
import os

import redis
from fastapi import APIRouter

from .tasks.ingest import ingest_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def _get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


@router.post("/ingest/trigger")
def trigger_ingest():
    """Manually trigger an ingestion cycle via Celery."""
    task = ingest_all.delay()
    return {"status": "triggered", "task_id": task.id}


@router.get("/ingest/status")
def ingest_status():
    """Get last ingestion run status."""
    r = _get_redis()
    stats = r.hgetall("hedge:ingest:stats")
    last_run = r.get("hedge:ingest:last_run")
    return {
        "last_run": last_run,
        "stats": stats or {},
    }

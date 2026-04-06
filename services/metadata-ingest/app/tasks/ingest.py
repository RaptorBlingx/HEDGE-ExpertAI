"""Celery task for periodic metadata ingestion."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
import redis

from ..celery_app import celery_app
from ..client import compute_checksum, get_client

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DISCOVERY_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")
MOCK_API_URL = os.getenv("MOCK_API_URL", "http://mock-api:9000")
HEDGE_API_URL = os.getenv("HEDGE_API_URL", "")

# Redis keys
CHECKSUM_PREFIX = "hedge:checksum:"
LAST_RUN_KEY = "hedge:ingest:last_run"
STATS_KEY = "hedge:ingest:stats"


def _get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


@celery_app.task(name="app.tasks.ingest.ingest_all", bind=True, max_retries=2)
def ingest_all(self):
    """Fetch all apps, detect changes via checksum, and index new/updated apps."""
    logger.info("Starting ingestion cycle")
    r = _get_redis()
    client = get_client(mock_url=MOCK_API_URL, hedge_url=HEDGE_API_URL or None)

    try:
        apps = client.fetch_all_apps()
    except Exception as exc:
        logger.error("Failed to fetch apps: %s", exc)
        raise self.retry(exc=exc, countdown=60)

    new_count = 0
    updated_count = 0
    unchanged_count = 0
    apps_to_index: list[dict] = []

    for app in apps:
        app_id = app.get("id", "")
        checksum = compute_checksum(app)
        stored_checksum = r.get(f"{CHECKSUM_PREFIX}{app_id}")

        if stored_checksum == checksum:
            unchanged_count += 1
            continue

        if stored_checksum is None:
            new_count += 1
        else:
            updated_count += 1

        r.set(f"{CHECKSUM_PREFIX}{app_id}", checksum)
        apps_to_index.append(app)

    # Batch index new/updated apps
    if apps_to_index:
        try:
            resp = httpx.post(
                f"{DISCOVERY_URL}/api/v1/apps/index",
                json={"apps": apps_to_index},
                timeout=120.0,
            )
            resp.raise_for_status()
            logger.info("Indexed %d apps via discovery-ranking", len(apps_to_index))
        except Exception as exc:
            logger.error("Failed to index apps: %s", exc)
            raise self.retry(exc=exc, countdown=30)

    now = datetime.now(timezone.utc).isoformat()
    stats = {
        "last_run": now,
        "total_fetched": len(apps),
        "new": new_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
    }
    r.set(LAST_RUN_KEY, now)
    r.hmset(STATS_KEY, stats)

    logger.info(
        "Ingestion complete: %d fetched, %d new, %d updated, %d unchanged",
        len(apps), new_count, updated_count, unchanged_count,
    )
    return stats

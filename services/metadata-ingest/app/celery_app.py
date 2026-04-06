"""Celery application configuration.

CRITICAL: include=["app.tasks.ingest"] must be explicit for autodiscovery to work.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
INGEST_INTERVAL = int(os.getenv("INGEST_INTERVAL_SECONDS", "7200"))

celery_app = Celery(
    "metadata_ingest",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.ingest"],  # MUST be explicit
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_max_tasks_per_child=50,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "periodic-ingest": {
            "task": "app.tasks.ingest.ingest_all",
            "schedule": INGEST_INTERVAL,
        },
    },
)

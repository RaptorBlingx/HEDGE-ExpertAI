"""Transactional catalogue ingestion and replay-safe index delivery."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx
from hedge_shared.models_v2 import AppMetadataV2
from hedge_shared.saref import validate_app_semantics
from hedge_shared.storage import (
    apply_data_retention,
    complete_ingestion_run,
    complete_outbox_item,
    create_ingestion_run,
    fail_outbox_item,
    pending_outbox,
    quarantine_item,
    tombstone_missing_apps,
    upsert_catalogue_app,
)
from pydantic import ValidationError

from ..celery_app import celery_app
from ..client import get_client

logger = logging.getLogger(__name__)

DISCOVERY_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")
MOCK_API_URL = os.getenv("MOCK_API_URL", "http://mock-api:9000")
HEDGE_API_URL = os.getenv("HEDGE_API_URL", "")


def _source_updated_at(app: AppMetadataV2) -> datetime | None:
    return app.lifecycle.updated_at or app.lifecycle.released_at


def deliver_pending_outbox(limit: int = 100) -> dict[str, int]:
    """Deliver claimed outbox operations and retain failures for retry."""
    delivered = 0
    failed = 0
    for item in pending_outbox(limit=limit):
        operation: dict[str, Any] = {
            "operation": item["operation"],
            "app_id": item["app_id"],
            "revision": item["revision"],
        }
        if item["operation"] == "upsert":
            operation["app"] = item["payload"]
        try:
            response = httpx.post(
                f"{DISCOVERY_URL}/api/v2/index/operations",
                json={"operations": [operation]},
                timeout=120.0,
            )
            response.raise_for_status()
            complete_outbox_item(
                item["id"],
                app_id=item["app_id"],
                revision=item["revision"],
            )
            delivered += 1
        except Exception as exc:
            logger.exception(
                "Index delivery failed for app=%s revision=%s",
                item["app_id"],
                item["revision"],
            )
            fail_outbox_item(item["id"], str(exc))
            failed += 1
    return {"delivered": delivered, "failed": failed}


@celery_app.task(name="app.tasks.ingest.deliver_outbox")
def deliver_outbox_task() -> dict[str, int]:
    """Replay pending vector operations independently of source ingestion."""
    return deliver_pending_outbox(limit=100)


@celery_app.task(name="app.tasks.ingest.apply_data_retention")
def apply_data_retention_task() -> dict[str, int]:
    """Roll up and erase expired pseudonymous and consented research data."""
    result = apply_data_retention()
    logger.info("Applied scheduled data retention: %s", result)
    return result


@celery_app.task(name="app.tasks.ingest.ingest_all", bind=True, max_retries=2)
def ingest_all(self: Any) -> dict[str, Any]:
    """Validate a complete source snapshot and transactionally enqueue changes."""
    source = HEDGE_API_URL or MOCK_API_URL
    run_id = create_ingestion_run(source)
    logger.info("Starting ingestion run %s from %s", run_id, source)
    client = get_client(mock_url=MOCK_API_URL, hedge_url=HEDGE_API_URL or None)

    try:
        raw_apps = client.fetch_all_apps()
    except Exception as exc:
        complete_ingestion_run(
            run_id,
            status="failed",
            fetched=0,
            created=0,
            updated=0,
            unchanged=0,
            deleted=0,
            quarantined=0,
            error=str(exc),
        )
        logger.exception("Failed to fetch source catalogue")
        raise self.retry(exc=exc, countdown=60) from exc

    counts = {"created": 0, "updated": 0, "unchanged": 0, "quarantined": 0}
    for position, raw in enumerate(raw_apps):
        source_key = str(raw.get("id") or f"position-{position}")
        try:
            app = AppMetadataV2.model_validate(raw)
            semantic_errors = validate_app_semantics(app)
            if semantic_errors:
                raise ValueError("; ".join(semantic_errors))
        except ValidationError as exc:
            quarantine_item(
                run_id,
                source_key=source_key,
                payload=raw,
                errors=exc.errors(include_url=False),
            )
            counts["quarantined"] += 1
            continue
        except ValueError as exc:
            quarantine_item(
                run_id,
                source_key=source_key,
                payload=raw,
                errors=[str(exc)],
            )
            counts["quarantined"] += 1
            continue

        action = upsert_catalogue_app(
            run_id,
            app,
            source_updated_at=_source_updated_at(app),
        )
        counts[action] += 1

    # A fetched snapshot is authoritative even when individual records are
    # quarantined: previously valid records absent from the snapshot are retired.
    deleted = tombstone_missing_apps(run_id)
    delivery = deliver_pending_outbox(limit=max(100, len(raw_apps) + deleted))
    status = "partial" if counts["quarantined"] or delivery["failed"] else "completed"
    complete_ingestion_run(
        run_id,
        status=status,
        fetched=len(raw_apps),
        created=counts["created"],
        updated=counts["updated"],
        unchanged=counts["unchanged"],
        deleted=deleted,
        quarantined=counts["quarantined"],
    )
    result = {
        "run_id": run_id,
        "status": status,
        "fetched": len(raw_apps),
        **counts,
        "deleted": deleted,
        "index_delivery": delivery,
    }
    logger.info("Ingestion run %s completed: %s", run_id, result)
    return result

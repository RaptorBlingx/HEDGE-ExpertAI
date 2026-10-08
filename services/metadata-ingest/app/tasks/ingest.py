"""Transactional catalogue ingestion and replay-safe index delivery."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from hedge_shared.storage import (
    apply_data_retention,
    complete_ingestion_run,
    complete_outbox_item,
    fail_outbox_item,
    pending_outbox,
)

from ..celery_app import celery_app
from ..client import get_client
from ..snapshot import reconcile_catalogue_snapshot

logger = logging.getLogger(__name__)

DISCOVERY_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")
MOCK_API_URL = os.getenv("MOCK_API_URL", "http://mock-api:9000")
HEDGE_API_URL = os.getenv("HEDGE_API_URL", "")


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
    """Reconcile the synthetic source; Store v1 transport remains unwired."""
    if HEDGE_API_URL:
        # Credentials/configuration do not authorize scheduled live ingestion.
        return {"status": "disabled", "reason": "Store v1 ingestion is not enabled"}
    source = MOCK_API_URL
    client = get_client(mock_url=MOCK_API_URL)
    try:
        result = reconcile_catalogue_snapshot(
            source,
            client.fetch_all_apps,
            # Only the mock's validated pagination establishes completeness.
            snapshot_complete=True,
        )
    except Exception as exc:
        logger.exception("Failed to reconcile source catalogue")
        raise self.retry(exc=exc, countdown=60) from exc

    delivery = deliver_pending_outbox(limit=max(100, result["fetched"] + result["deleted"]))
    if delivery["failed"]:
        result["status"] = "partial"
        complete_ingestion_run(
            result["run_id"],
            status="partial",
            fetched=result["fetched"],
            created=result["created"],
            updated=result["updated"],
            unchanged=result["unchanged"],
            deleted=result["deleted"],
            quarantined=result["quarantined"],
        )
    result["index_delivery"] = delivery
    logger.info("Ingestion run %s completed: %s", result["run_id"], result)
    return result

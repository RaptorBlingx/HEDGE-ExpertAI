"""Administrative ingestion routes."""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Security
from fastapi.security import APIKeyHeader
from hedge_shared.storage import (
    get_ingestion_run,
    latest_ingestion_run,
    list_quarantined_items,
    outbox_status,
    retry_outbox_item,
)

from .tasks.ingest import deliver_outbox_task, ingest_all

router = APIRouter()
_admin_key = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_admin_key(api_key: str | None = Security(_admin_key)) -> None:
    """Reuse the gateway's administrative key at the internal HTTP boundary."""
    expected = os.getenv("GATEWAY_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=503, detail="Ingestion administrative access is not configured."
        )
    if api_key is None or not hmac.compare_digest(api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing administrative API key.")


@router.post("/api/v1/ingest/trigger", dependencies=[Depends(_require_admin_key)])
@router.post("/api/v2/ingestion/runs", status_code=202, dependencies=[Depends(_require_admin_key)])
def trigger_ingest() -> dict[str, str]:
    """Queue a complete catalogue ingestion run."""
    task = ingest_all.delay()
    return {"status": "queued", "task_id": task.id}


@router.post(
    "/api/v2/ingestion/outbox/replay", status_code=202, dependencies=[Depends(_require_admin_key)]
)
def replay_outbox(outbox_id: int | None = Query(default=None, ge=1)) -> dict[str, str]:
    """Replay due work, or explicitly release one exhausted operation."""
    if outbox_id is not None and not retry_outbox_item(outbox_id):
        raise HTTPException(status_code=409, detail="Outbox item is not an exhausted failure")
    task = deliver_outbox_task.delay()
    return {"status": "queued", "task_id": task.id}


@router.get("/api/v1/ingest/status")
@router.get("/api/v2/ingestion/runs/latest")
def ingest_status() -> dict:
    """Return the latest durable ingestion run."""
    run = latest_ingestion_run()
    if run is None:
        return {"status": "not_run", "run": None, "outbox": outbox_status()}
    return {"status": run["status"], "run": run, "outbox": outbox_status()}


@router.get("/api/v2/ingestion/runs/{run_id}")
def ingestion_run(run_id: str = Path(min_length=36, max_length=36)) -> dict:
    """Return a specific durable run, not merely the most recent run."""
    run = get_ingestion_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return {"run": run}


@router.get("/api/v2/ingestion/quarantine")
def quarantine(
    run_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> dict:
    """Page validation errors without returning quarantined source payloads."""
    total, items = list_quarantined_items(
        run_id=run_id,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}

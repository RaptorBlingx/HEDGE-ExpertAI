"""Administrative ingestion routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query
from hedge_shared.storage import get_ingestion_run, latest_ingestion_run, list_quarantined_items

from .tasks.ingest import deliver_outbox_task, ingest_all

router = APIRouter()


@router.post("/api/v1/ingest/trigger")
@router.post("/api/v2/ingestion/runs", status_code=202)
def trigger_ingest() -> dict[str, str]:
    """Queue a complete catalogue ingestion run."""
    task = ingest_all.delay()
    return {"status": "queued", "task_id": task.id}


@router.post("/api/v2/ingestion/outbox/replay", status_code=202)
def replay_outbox() -> dict[str, str]:
    """Queue retry of failed or pending index operations."""
    task = deliver_outbox_task.delay()
    return {"status": "queued", "task_id": task.id}


@router.get("/api/v1/ingest/status")
@router.get("/api/v2/ingestion/runs/latest")
def ingest_status() -> dict:
    """Return the latest durable ingestion run."""
    run = latest_ingestion_run()
    if run is None:
        return {"status": "not_run", "run": None}
    return {"status": run["status"], "run": run}


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

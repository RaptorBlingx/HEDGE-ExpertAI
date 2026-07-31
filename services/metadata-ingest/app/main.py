"""Metadata ingestion API entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Response, status
from hedge_shared.metrics import MetricsMiddleware
from hedge_shared.storage import latest_ingestion_run, ping_database

from .routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

app = FastAPI(
    title="HEDGE-ExpertAI Metadata Ingest",
    version="2.0.0",
)
app.add_middleware(MetricsMiddleware, service_name="metadata-ingest")
app.include_router(router)


@app.get("/live")
def live() -> dict[str, str]:
    """Process liveness independent of dependencies."""
    return {"status": "ok", "service": "metadata-ingest"}


@app.get("/ready")
def ready(response: Response) -> dict:
    """Dependency and first-run readiness."""
    database_ok = ping_database()
    run = latest_ingestion_run() if database_ok else None
    ready_state = database_ok and run is not None and run["status"] in {"completed", "partial"}
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready_state else "not_ready",
        "service": "metadata-ingest",
        "database": database_ok,
        "last_run_status": run["status"] if run else None,
    }


@app.get("/health")
def health(response: Response) -> dict:
    """Compatibility alias for readiness."""
    return ready(response)

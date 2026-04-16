"""Metadata Ingest — FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI

from .routes import router

try:
    from hedge_shared.metrics import MetricsMiddleware
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(
    title="HEDGE-ExpertAI Metadata Ingest",
    version="0.1.0",
)

if _HAS_METRICS:
    app.add_middleware(MetricsMiddleware, service_name="metadata-ingest")

app.include_router(router)

# Maximum age (seconds) of the last successful ingest before health degrades.
# Default: 3× the ingest interval (2 h) → 6 h gives plenty of margin.
_CELERY_STALE_THRESHOLD = int(os.getenv("CELERY_STALE_SECONDS", "21600"))


@app.get("/health")
def health():
    """Health check — verifies Redis connectivity AND Celery beat freshness."""
    import redis as redis_lib

    try:
        r = redis_lib.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
        r.ping()
    except Exception as e:
        return {"status": "degraded", "service": "metadata-ingest", "error": f"redis: {e}"}

    # Verify Celery beat is still scheduling runs
    last_run_iso = r.get("hedge:ingest:last_run")
    celery_ok = True
    celery_note = "no run recorded yet"
    if last_run_iso:
        try:
            last_run_dt = datetime.fromisoformat(last_run_iso)
            age_s = (datetime.now(timezone.utc) - last_run_dt).total_seconds()
            celery_note = f"last_run {int(age_s)}s ago"
            if age_s > _CELERY_STALE_THRESHOLD:
                celery_ok = False
                celery_note += " (STALE — celery beat may have crashed)"
        except Exception:
            celery_note = f"unparseable timestamp: {last_run_iso}"

    status = "ok" if celery_ok else "degraded"
    return {
        "status": status,
        "service": "metadata-ingest",
        "version": "0.1.0",
        "celery_beat": celery_note,
    }

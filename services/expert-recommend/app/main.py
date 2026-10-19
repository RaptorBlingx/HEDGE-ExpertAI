"""Expert Recommend — FastAPI application entry point."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import FastAPI, Response, status

from .routes import router, v2_router

try:
    from hedge_shared.metrics import MetricsMiddleware
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


app = FastAPI(
    title="HEDGE-ExpertAI Expert Recommend",
    version="2.0.0",
)

if _HAS_METRICS:
    app.add_middleware(MetricsMiddleware, service_name="expert-recommend")

app.include_router(router)
app.include_router(v2_router)


@app.get("/health")
def health(response: Response):
    """Routine readiness depends on retrieval; generation is optional."""
    discovery_ok = False
    try:
        discovery_url = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")
        discovery_ok = httpx.get(f"{discovery_url}/ready", timeout=5.0).status_code == 200
    except Exception:
        logging.exception("Discovery health check failed")
    ready_state = discovery_ok
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready_state else "degraded",
        "service": "expert-recommend",
        "version": "2.0.0",
        "ollama": "optional",
        "discovery": discovery_ok,
    }


@app.get("/live")
def live():
    return {"status": "ok", "service": "expert-recommend"}


@app.get("/ready")
def ready(response: Response):
    return health(response)

"""Gateway — FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from hedge_shared.production import validate_production_environment

from .middleware import (
    APIKeyMiddleware,
    JWTAuthMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from .routes import _SERVICES, router

try:
    from hedge_shared.metrics import MetricsMiddleware
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Validate the production trust boundary before accepting traffic."""
    validate_production_environment()
    yield

app = FastAPI(
    title="HEDGE-ExpertAI Gateway",
    version="2.0.0",
    description="API Gateway for HEDGE-ExpertAI services",
    lifespan=lifespan,
)

# CORS — restrict origins in production via CORS_ALLOWED_ORIGINS env var.
# Accepts comma-separated list; defaults to permissive for local development.
_allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)

# Custom middleware (order matters: first added = outermost)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(JWTAuthMiddleware)
if _HAS_METRICS:
    app.add_middleware(MetricsMiddleware, service_name="gateway")

app.include_router(router)


@app.get("/health")
def health(response: Response):
    """Aggregated health check across all services."""
    statuses = {"gateway": "ok"}
    overall = "ok"

    for name, url in _SERVICES.items():
        try:
            resp = httpx.get(url, timeout=5.0)
            data = resp.json()
            statuses[name] = data.get("status", "unknown")
            if resp.status_code >= 400 or data.get("status") != "ok":
                overall = "degraded"
        except Exception:
            statuses[name] = "down"
            overall = "degraded"

    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": overall,
        "service": "gateway",
        "version": "2.0.0",
        "services": statuses,
    }


@app.get("/live")
def live():
    return {"status": "ok", "service": "gateway"}


@app.get("/ready")
def ready(response: Response):
    return health(response)


# Serve frontend static files if available.
# Keep this after API route declarations so /health and /api/* are not shadowed.
_FRONTEND_DIR = "/app/static"
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="static")

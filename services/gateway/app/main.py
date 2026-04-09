"""Gateway — FastAPI application entry point."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .middleware import APIKeyMiddleware, RateLimitMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from .routes import router, _SERVICES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="HEDGE-ExpertAI Gateway",
    version="0.1.0",
    description="API Gateway for HEDGE-ExpertAI services",
)

# CORS — restrict origins in production via CORS_ALLOWED_ORIGINS env var.
# Accepts comma-separated list; defaults to permissive for local development.
_allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
)

# Custom middleware (order matters: first added = outermost)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
app.add_middleware(APIKeyMiddleware)

app.include_router(router)


@app.get("/health")
def health():
    """Aggregated health check across all services."""
    statuses = {"gateway": "ok"}
    overall = "ok"

    for name, url in _SERVICES.items():
        try:
            resp = httpx.get(url, timeout=5.0)
            data = resp.json()
            statuses[name] = data.get("status", "unknown")
            if data.get("status") != "ok":
                overall = "degraded"
        except Exception:
            statuses[name] = "down"
            overall = "degraded"

    return {
        "status": overall,
        "service": "gateway",
        "version": "0.1.0",
        "services": statuses,
    }


# Serve frontend static files if available.
# Keep this after API route declarations so /health and /api/* are not shadowed.
_FRONTEND_DIR = "/app/static"
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="static")

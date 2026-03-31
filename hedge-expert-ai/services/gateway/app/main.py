"""Gateway — FastAPI application entry point."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .middleware import RateLimitMiddleware, RequestIDMiddleware, SecurityHeadersMiddleware
from .routes import router, _SERVICES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="HEDGE-ExpertAI Gateway",
    version="0.1.0",
    description="API Gateway for HEDGE-ExpertAI services",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware (order matters: first added = outermost)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

app.include_router(router)

# Serve frontend static files if available
_FRONTEND_DIR = "/app/static"
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="static")


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

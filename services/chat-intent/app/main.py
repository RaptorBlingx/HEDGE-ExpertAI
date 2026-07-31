"""Chat Intent — FastAPI application entry point."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Response, status
from hedge_shared.storage import ping_database

from .routes import router, v2_router

try:
    from hedge_shared.metrics import MetricsMiddleware
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(
    title="HEDGE-ExpertAI Chat & Intent",
    version="2.0.0",
)

if _HAS_METRICS:
    app.add_middleware(MetricsMiddleware, service_name="chat-intent")

app.include_router(router)
app.include_router(v2_router)


@app.get("/health")
def health(response: Response):
    """Health check — verifies operational sessions and durable events."""
    import redis as redis_lib

    try:
        r = redis_lib.from_url(
            os.getenv(
                "VALKEY_SESSION_URL",
                os.getenv("REDIS_URL", "redis://valkey-cache:6379/0"),
            )
        )
        valkey_ok = bool(r.ping())
    except Exception:
        valkey_ok = False
        logging.exception("Valkey health check failed")
    postgres_ok = ping_database()
    ready_state = valkey_ok and postgres_ok
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready_state else "degraded",
        "service": "chat-intent",
        "version": "2.0.0",
        "postgres": postgres_ok,
        "valkey": valkey_ok,
    }


@app.get("/live")
def live():
    return {"status": "ok", "service": "chat-intent"}


@app.get("/ready")
def ready(response: Response):
    return health(response)

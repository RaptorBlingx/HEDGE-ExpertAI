"""Chat Intent — FastAPI application entry point."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI

from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(
    title="HEDGE-ExpertAI Chat & Intent",
    version="0.1.0",
)

app.include_router(router)


@app.get("/health")
def health():
    """Health check — verifies Redis connectivity."""
    import redis as redis_lib

    try:
        r = redis_lib.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        r.ping()
        return {"status": "ok", "service": "chat-intent", "version": "0.1.0"}
    except Exception as e:
        return {"status": "degraded", "service": "chat-intent", "error": str(e)}

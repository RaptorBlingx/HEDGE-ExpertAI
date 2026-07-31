"""Discovery & Ranking — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from hedge_shared.storage import ping_database

from .indexer import ensure_collection, get_client
from .routes import router, v2_router

try:
    from hedge_shared.metrics import MetricsMiddleware
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize Qdrant and preload the pinned embedding model."""
    import os

    host = os.getenv("QDRANT_HOST", "qdrant")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    client = get_client(host=host, port=port)
    ensure_collection(client)

    from .embeddings import encode_single

    encode_single("warmup")
    logger.info("Discovery-Ranking service ready (embeddings preloaded)")
    yield

app = FastAPI(
    title="HEDGE-ExpertAI Discovery & Ranking",
    version="2.0.0",
    lifespan=lifespan,
)

if _HAS_METRICS:
    app.add_middleware(MetricsMiddleware, service_name="discovery-ranking")

app.include_router(router)
app.include_router(v2_router)


@app.get("/health")
def health(response: Response):
    """Health check — verifies authoritative and derived stores."""
    qdrant_ok = False
    try:
        client = get_client()
        client.get_collections()
        qdrant_ok = True
    except Exception:
        logger.exception("Qdrant health check failed")
    postgres_ok = ping_database()
    ready_state = qdrant_ok and postgres_ok
    if not ready_state:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if ready_state else "degraded",
        "service": "discovery-ranking",
        "version": "2.0.0",
        "postgres": postgres_ok,
        "qdrant": qdrant_ok,
    }


@app.get("/live")
def live():
    """Process liveness."""
    return {"status": "ok", "service": "discovery-ranking"}


@app.get("/ready")
def ready(response: Response):
    """Dependency readiness."""
    return health(response)

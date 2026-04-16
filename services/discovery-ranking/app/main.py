"""Discovery & Ranking — FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .indexer import ensure_collection, get_client
from .routes import router

try:
    from hedge_shared.metrics import MetricsMiddleware
    _HAS_METRICS = True
except ImportError:
    _HAS_METRICS = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="HEDGE-ExpertAI Discovery & Ranking",
    version="0.1.0",
)

if _HAS_METRICS:
    app.add_middleware(MetricsMiddleware, service_name="discovery-ranking")

app.include_router(router)


@app.on_event("startup")
async def startup():
    """Initialize Qdrant connection, ensure collection, and preload embeddings."""
    import os

    host = os.getenv("QDRANT_HOST", "qdrant")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    client = get_client(host=host, port=port)
    ensure_collection(client)

    # Preload embedding model to avoid cold-start latency on first search
    from .embeddings import encode_single
    encode_single("warmup")

    logger.info("Discovery-Ranking service ready (embeddings preloaded)")


@app.get("/health")
def health():
    """Health check — verifies Qdrant connectivity."""
    try:
        client = get_client()
        client.get_collections()
        return {"status": "ok", "service": "discovery-ranking", "version": "0.1.0"}
    except Exception as e:
        return {"status": "degraded", "service": "discovery-ranking", "error": str(e)}

"""Expert Recommend — FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .llm_client import OllamaClient
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(
    title="HEDGE-ExpertAI Expert Recommend",
    version="0.1.0",
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    """Warm up the Ollama model so it is loaded for the first request."""
    import threading

    def _warmup():
        client = OllamaClient()
        client.warmup()

    # Run warmup in background thread to not block startup
    threading.Thread(target=_warmup, daemon=True).start()


@app.get("/health")
def health():
    """Health check — verifies Ollama connectivity."""
    client = OllamaClient()
    if client.is_healthy():
        return {"status": "ok", "service": "expert-recommend", "version": "0.1.0"}
    return {"status": "degraded", "service": "expert-recommend", "error": "ollama unreachable"}

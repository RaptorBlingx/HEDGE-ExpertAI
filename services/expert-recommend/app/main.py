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


@app.get("/health")
def health():
    """Health check — verifies Ollama connectivity."""
    client = OllamaClient()
    if client.is_healthy():
        return {"status": "ok", "service": "expert-recommend", "version": "0.1.0"}
    return {"status": "degraded", "service": "expert-recommend", "error": "ollama unreachable"}

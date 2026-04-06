"""Gateway — reverse proxy routes to internal services."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

CHAT_INTENT_URL = os.getenv("CHAT_INTENT_URL", "http://chat-intent:8001")
DISCOVERY_RANKING_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")
METADATA_INGEST_URL = os.getenv("METADATA_INGEST_URL", "http://metadata-ingest:8004")

# Service URLs for health aggregation
_SERVICES = {
    "chat-intent": f"{CHAT_INTENT_URL}/health",
    "expert-recommend": os.getenv("EXPERT_RECOMMEND_URL", "http://expert-recommend:8002") + "/health",
    "discovery-ranking": f"{DISCOVERY_RANKING_URL}/health",
    "metadata-ingest": f"{METADATA_INGEST_URL}/health",
}


@router.post("/api/v1/chat")
async def proxy_chat(request: Request):
    """Proxy chat requests to chat-intent service."""
    body = await request.json()
    try:
        resp = httpx.post(
            f"{CHAT_INTENT_URL}/api/v1/chat",
            json=body,
            timeout=300.0,  # LLM-backed, can be slow
        )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        logger.exception("Chat proxy failed")
        return JSONResponse(
            status_code=502,
            content={"detail": "Chat service unavailable"},
        )


@router.post("/api/v1/apps/search")
async def proxy_search(request: Request):
    """Proxy search requests to discovery-ranking service."""
    body = await request.json()
    try:
        resp = httpx.post(
            f"{DISCOVERY_RANKING_URL}/api/v1/apps/search",
            json=body,
            timeout=30.0,
        )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        logger.exception("Search proxy failed")
        return JSONResponse(
            status_code=502,
            content={"detail": "Search service unavailable"},
        )


@router.get("/api/v1/apps/{app_id}")
async def proxy_get_app(app_id: str):
    """Proxy app detail requests to discovery-ranking service."""
    try:
        resp = httpx.get(
            f"{DISCOVERY_RANKING_URL}/api/v1/apps/{app_id}",
            timeout=10.0,
        )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        logger.exception("App detail proxy failed")
        return JSONResponse(
            status_code=502,
            content={"detail": "Discovery service unavailable"},
        )


@router.post("/api/v1/ingest/trigger")
async def proxy_ingest_trigger():
    """Proxy ingest trigger to metadata-ingest service."""
    try:
        resp = httpx.post(
            f"{METADATA_INGEST_URL}/api/v1/ingest/trigger",
            timeout=30.0,
        )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        logger.exception("Ingest trigger proxy failed")
        return JSONResponse(
            status_code=502,
            content={"detail": "Ingest service unavailable"},
        )


@router.get("/api/v1/ingest/status")
async def proxy_ingest_status():
    """Proxy ingest status to metadata-ingest service."""
    try:
        resp = httpx.get(
            f"{METADATA_INGEST_URL}/api/v1/ingest/status",
            timeout=10.0,
        )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        return JSONResponse(
            status_code=502,
            content={"detail": "Ingest service unavailable"},
        )

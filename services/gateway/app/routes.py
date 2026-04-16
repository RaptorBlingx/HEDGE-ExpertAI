"""Gateway — reverse proxy routes to internal services."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter()

CHAT_INTENT_URL = os.getenv("CHAT_INTENT_URL", "http://chat-intent:8001")
DISCOVERY_RANKING_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")
METADATA_INGEST_URL = os.getenv("METADATA_INGEST_URL", "http://metadata-ingest:8004")
MOCK_API_URL = os.getenv("MOCK_API_URL", "http://mock-api:9000")

# Service URLs for health aggregation
_SERVICES = {
    "chat-intent": f"{CHAT_INTENT_URL}/health",
    "expert-recommend": os.getenv("EXPERT_RECOMMEND_URL", "http://expert-recommend:8002") + "/health",
    "discovery-ranking": f"{DISCOVERY_RANKING_URL}/health",
    "metadata-ingest": f"{METADATA_INGEST_URL}/health",
    "mock-api": f"{MOCK_API_URL}/health",
}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_roles(name: str, default: str) -> set[str]:
    raw = os.getenv(name, default)
    return {item.strip() for item in raw.split(",") if item.strip()}


def _require_roles(request: Request, allowed_roles: set[str]) -> None:
    if not _env_flag("ENABLE_RBAC"):
        return
    if getattr(request.state, "api_key_authenticated", False):
        return

    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Bearer token required.")

    user_roles = set(getattr(user, "roles", []))
    if not user_roles.intersection(allowed_roles):
        raise HTTPException(status_code=403, detail="Insufficient role for this endpoint.")


def _require_admin(request: Request) -> None:
    _require_roles(request, _env_roles("RBAC_ADMIN_ROLES", "admin,administrator"))


def _require_analyst(request: Request) -> None:
    _require_roles(request, _env_roles("RBAC_ANALYST_ROLES", "analyst,admin"))


@router.post("/api/v1/chat")
async def proxy_chat(request: Request):
    """Proxy chat requests to chat-intent service."""
    body = await request.json()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
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


@router.post("/api/v1/chat/stream")
async def proxy_chat_stream(request: Request):
    """Proxy streaming chat requests to chat-intent service via SSE."""
    import json as _json

    body = await request.json()

    async def _proxy():
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{CHAT_INTENT_URL}/api/v1/chat/stream",
                    json=body,
                    timeout=300.0,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"{line}\n\n"
        except Exception:
            logger.exception("Chat stream proxy failed")
            yield f"data: {_json.dumps({'type': 'error', 'content': 'Chat service unavailable'})}\n\n"

    return StreamingResponse(
        _proxy(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/v1/apps/search")
async def proxy_search(request: Request):
    """Proxy search requests to discovery-ranking service."""
    body = await request.json()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
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


@router.get("/api/v1/catalog/apps")
async def proxy_catalog_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
):
    """Proxy app catalog listing to mock-api for frontend manual review."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MOCK_API_URL}/api/apps",
                params={"page": page, "page_size": page_size},
                timeout=20.0,
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        logger.exception("Catalog list proxy failed")
        return JSONResponse(
            status_code=502,
            content={"detail": "Catalog service unavailable"},
        )


@router.get("/api/v1/catalog/apps/search")
async def proxy_catalog_search(q: str = Query(..., min_length=1)):
    """Proxy app catalog keyword search to mock-api."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MOCK_API_URL}/api/apps/search",
                params={"q": q},
                timeout=20.0,
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        logger.exception("Catalog search proxy failed")
        return JSONResponse(
            status_code=502,
            content={"detail": "Catalog service unavailable"},
        )


@router.get("/api/v1/catalog/apps/{app_id}")
async def proxy_catalog_app(app_id: str):
    """Proxy app catalog detail to mock-api."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MOCK_API_URL}/api/apps/{app_id}",
                timeout=20.0,
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        logger.exception("Catalog detail proxy failed")
        return JSONResponse(
            status_code=502,
            content={"detail": "Catalog service unavailable"},
        )


@router.get("/api/v1/apps/{app_id}")
async def proxy_get_app(app_id: str):
    """Proxy app detail requests to discovery-ranking service."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
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
async def proxy_ingest_trigger(request: Request):
    """Proxy ingest trigger to metadata-ingest service."""
    _require_admin(request)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
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
async def proxy_ingest_status(request: Request):
    """Proxy ingest status to metadata-ingest service."""
    _require_analyst(request)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{METADATA_INGEST_URL}/api/v1/ingest/status",
                timeout=10.0,
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        return JSONResponse(
            status_code=502,
            content={"detail": "Ingest service unavailable"},
        )


# ---------------------------------------------------------------------------
# Feedback proxy
# ---------------------------------------------------------------------------
@router.post("/api/v1/feedback")
async def proxy_feedback(request: Request):
    """Proxy feedback submission to chat-intent service."""
    body = await request.json()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{CHAT_INTENT_URL}/api/v1/feedback",
                json=body,
                timeout=10.0,
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        logger.exception("Feedback proxy failed")
        return JSONResponse(
            status_code=502,
            content={"detail": "Feedback service unavailable"},
        )


@router.get("/api/v1/feedback/stats")
async def proxy_feedback_stats(request: Request):
    """Proxy feedback stats for KPI reporting."""
    _require_analyst(request)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{CHAT_INTENT_URL}/api/v1/feedback/stats",
                timeout=10.0,
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        return JSONResponse(
            status_code=502,
            content={"detail": "Feedback service unavailable"},
        )


# ---------------------------------------------------------------------------
# Session recording proxy (Obj 5)
# ---------------------------------------------------------------------------
@router.get("/api/v1/sessions/recorded")
async def proxy_sessions_list(request: Request, limit: int = Query(100, ge=1, le=1000)):
    """List recorded sessions."""
    _require_analyst(request)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{CHAT_INTENT_URL}/api/v1/sessions/recorded",
                params={"limit": limit},
                timeout=10.0,
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        return JSONResponse(
            status_code=502,
            content={"detail": "Session service unavailable"},
        )


@router.get("/api/v1/sessions/recorded/{session_id}")
async def proxy_session_log(session_id: str, request: Request):
    """Get full event log for a recorded session."""
    _require_analyst(request)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{CHAT_INTENT_URL}/api/v1/sessions/recorded/{session_id}",
                timeout=10.0,
            )
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception:
        return JSONResponse(
            status_code=502,
            content={"detail": "Session service unavailable"},
        )

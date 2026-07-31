"""Gateway — reverse proxy routes to internal services."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from hedge_shared.models_v2 import (
    ChatRequestV2,
    RecommendationEventRequest,
    ReindexRequestV2,
    SearchRequestV2,
)

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


def _problem(status_code: int, title: str, detail: str | None = None) -> JSONResponse:
    content = {"type": "about:blank", "title": title, "status": status_code}
    if detail:
        content["detail"] = detail
    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type="application/problem+json",
    )


def _json_upstream(response: httpx.Response, service: str) -> JSONResponse:
    """Preserve status and safe JSON errors without assuming every body is JSON."""
    try:
        content = response.json()
    except ValueError:
        content = {
            "type": "about:blank",
            "title": f"{service} returned an invalid response",
            "status": response.status_code,
        }
    media_type = (
        "application/problem+json"
        if response.status_code >= 400
        else "application/json"
    )
    return JSONResponse(
        status_code=response.status_code,
        content=content,
        media_type=media_type,
    )


async def _post_json(url: str, payload: dict, service: str, timeout: float) -> JSONResponse:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=timeout)
        return _json_upstream(response, service)
    except Exception:
        logger.exception("%s request failed", service)
        return _problem(502, f"{service} unavailable")


async def _get_json(
    url: str,
    service: str,
    *,
    params: dict | None = None,
    timeout: float = 20.0,
) -> JSONResponse:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=timeout)
        return _json_upstream(response, service)
    except Exception:
        logger.exception("%s request failed", service)
        return _problem(502, f"{service} unavailable")


# ---------------------------------------------------------------------------
# Version 2 public contracts
# ---------------------------------------------------------------------------


@router.post("/api/v2/chat")
async def proxy_chat_v2(body: ChatRequestV2):
    """Proxy strict v2 chat requests."""
    return await _post_json(
        f"{CHAT_INTENT_URL}/api/v2/chat",
        body.model_dump(mode="json"),
        "Chat service",
        300.0,
    )


@router.post(
    "/api/v2/chat/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def proxy_chat_stream_v2(body: ChatRequestV2):
    """Proxy v2 SSE without altering event boundaries or upstream status."""

    async def stream():
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{CHAT_INTENT_URL}/api/v2/chat/stream",
                    json=body.model_dump(mode="json"),
                    timeout=300.0,
                ) as response:
                    if response.status_code >= 400:
                        payload = {
                            "type": "problem",
                            "title": "Chat service rejected the request",
                            "status": response.status_code,
                        }
                        import json

                        yield f"event: problem\ndata: {json.dumps(payload)}\n\n".encode()
                        return
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except Exception:
            logger.exception("V2 chat stream proxy failed")
            import json

            payload = {
                "type": "problem",
                "title": "Chat service unavailable",
                "status": 502,
            }
            yield f"event: problem\ndata: {json.dumps(payload)}\n\n".encode()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/v2/apps/search")
async def proxy_search_v2(body: SearchRequestV2):
    """Proxy typed multilingual search."""
    return await _post_json(
        f"{DISCOVERY_RANKING_URL}/api/v2/apps/search",
        body.model_dump(mode="json"),
        "Discovery service",
        30.0,
    )


@router.get("/api/v2/catalog/apps")
async def proxy_catalog_v2(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """List authoritative v2 catalogue records."""
    return await _get_json(
        f"{DISCOVERY_RANKING_URL}/api/v2/catalog/apps",
        "Catalogue service",
        params={"page": page, "page_size": page_size},
    )


@router.get("/api/v2/catalog/apps/{app_id}.jsonld")
async def proxy_catalog_jsonld_v2(app_id: str):
    """Return authoritative JSON-LD through the public gateway."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{DISCOVERY_RANKING_URL}/api/v2/catalog/apps/{app_id}.jsonld",
                timeout=20.0,
            )
        return JSONResponse(
            status_code=response.status_code,
            content=response.json(),
            media_type=(
                "application/ld+json"
                if response.status_code < 400
                else "application/problem+json"
            ),
        )
    except Exception:
        logger.exception("JSON-LD catalogue request failed")
        return _problem(502, "Catalogue service unavailable")


@router.get("/api/v2/catalog/apps/{app_id}")
async def proxy_catalog_app_v2(app_id: str):
    """Return authoritative v2 catalogue detail."""
    return await _get_json(
        f"{DISCOVERY_RANKING_URL}/api/v2/catalog/apps/{app_id}",
        "Catalogue service",
    )


@router.post("/api/v2/recommendation-events", status_code=201)
async def proxy_recommendation_event(body: RecommendationEventRequest):
    """Record verified response-level or app-open telemetry."""
    return await _post_json(
        f"{CHAT_INTENT_URL}/api/v2/recommendation-events",
        body.model_dump(mode="json"),
        "Recommendation event service",
        10.0,
    )


@router.delete("/api/v2/sessions/{session_id}")
async def proxy_session_delete_v2(session_id: str):
    """Delete operational session state."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{CHAT_INTENT_URL}/api/v2/sessions/{session_id}",
                timeout=10.0,
            )
        return _json_upstream(response, "Session service")
    except Exception:
        logger.exception("Session deletion failed")
        return _problem(502, "Session service unavailable")


@router.get("/api/v2/analytics/recommendations")
async def proxy_recommendation_analytics(request: Request):
    """Analyst-only durable KPI summary."""
    _require_analyst(request)
    return await _get_json(
        f"{CHAT_INTENT_URL}/api/v2/analytics/recommendations",
        "Analytics service",
        timeout=10.0,
    )


@router.post("/api/v2/ingestion/runs", status_code=202)
async def proxy_ingestion_run_v2(request: Request):
    """Admin-only ingestion trigger."""
    _require_admin(request)
    return await _post_json(
        f"{METADATA_INGEST_URL}/api/v2/ingestion/runs",
        {},
        "Ingestion service",
        30.0,
    )


@router.get("/api/v2/ingestion/runs/latest")
async def proxy_latest_ingestion_v2(request: Request):
    """Analyst-only ingestion status."""
    _require_analyst(request)
    return await _get_json(
        f"{METADATA_INGEST_URL}/api/v2/ingestion/runs/latest",
        "Ingestion service",
        timeout=10.0,
    )


@router.get("/api/v2/ingestion/runs/{run_id}")
async def proxy_ingestion_run_detail_v2(
    request: Request,
    run_id: str = Path(min_length=36, max_length=36),
):
    """Analyst-only durable ingestion-run detail."""
    _require_analyst(request)
    return await _get_json(
        f"{METADATA_INGEST_URL}/api/v2/ingestion/runs/{run_id}",
        "Ingestion service",
        timeout=10.0,
    )


@router.get("/api/v2/ingestion/quarantine")
async def proxy_ingestion_quarantine_v2(
    request: Request,
    run_id: str | None = Query(default=None, min_length=36, max_length=36),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    """Analyst-only validation failures without quarantined source payloads."""
    _require_analyst(request)
    params = {"page": page, "page_size": page_size}
    if run_id is not None:
        params["run_id"] = run_id
    return await _get_json(
        f"{METADATA_INGEST_URL}/api/v2/ingestion/quarantine",
        "Ingestion service",
        params=params,
        timeout=10.0,
    )


@router.post("/api/v2/ingestion/outbox/replay", status_code=202)
async def proxy_ingestion_outbox_replay_v2(request: Request):
    """Admin-only replay of pending and failed index operations."""
    _require_admin(request)
    return await _post_json(
        f"{METADATA_INGEST_URL}/api/v2/ingestion/outbox/replay",
        {},
        "Ingestion service",
        30.0,
    )


@router.post("/api/v2/index/rebuild")
async def proxy_reindex_v2(request: Request, body: ReindexRequestV2):
    """Admin-only full rebuild followed by atomic collection alias promotion."""
    _require_admin(request)
    return await _post_json(
        f"{DISCOVERY_RANKING_URL}/api/v2/index/rebuild",
        body.model_dump(mode="json"),
        "Discovery service",
        600.0,
    )


@router.post("/api/v2/index/promote")
async def proxy_index_promotion_v2(request: Request, body: ReindexRequestV2):
    """Admin-only atomic roll forward or rollback to a validated collection."""
    _require_admin(request)
    return await _post_json(
        f"{DISCOVERY_RANKING_URL}/api/v2/index/promote",
        body.model_dump(mode="json"),
        "Discovery service",
        60.0,
    )


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

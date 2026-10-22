"""Private widget delivery and HTTP proxies, without an in-process service bridge."""
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from hedge_shared.config import Settings

router = APIRouter()
ROOT = Path(os.environ.get("PRIVATE_STORE_SOURCE", "/source"))


async def upstream(service, path, body=None):
    try:
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            response = await client.request("GET" if body is None else "POST",
                os.environ[service] + path, json=body,
                headers={"X-API-Key": os.environ["GATEWAY_API_KEY"]})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Store service unavailable") from None


@router.get("/")
def home():
    return FileResponse(ROOT / "frontend/private-store/index.html")


@router.get("/favicon.ico", status_code=204)
def favicon():
    return None


@router.get("/api/v2/status")
async def status():
    state = await upstream("METADATA_INGEST_URL", "/internal/store/status")
    source_kind = state.get("synchronization", {}).get("source_kind", "none")
    return {"source": source_kind, "catalogue": ("Authorized HEDGE Store applications" if source_kind == "authorized_api"
                          else "Saved authorized Store observation" if source_kind == "authorized_snapshot"
                          else "Authored evaluation catalogue — not live Store evidence" if source_kind == "authored_evaluation_fixture"
                          else "Store catalogue not initialized"),
            "intent": "Real Rasa over HTTP", "embeddings": "Pinned E5 and private Qdrant",
            "generation": ("Source answers; model choice between readings and review of paraphrases"
                           if Settings().STORE_SEMANTIC_ENABLED else "Source answers; no model calls"),
            "managed_workspace": True, "simulation_controls": False,
            "deployed_commit": os.environ.get("DEPLOYED_COMMIT", "unknown"), **state}


@router.get("/api/v2/catalogue")
async def catalogue(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=50)):
    data = await upstream("DISCOVERY_RANKING_URL", "/internal/store/catalogue", {})
    rows = sorted(data["apps"], key=lambda app: app["app_id"])
    return {"total": len(rows), "offset": offset,
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "apps": [{k: row.get(k) for k in ("id", "app_id", "store_id", "name", "provider")}
                     for row in rows[offset:offset + limit]]}


@router.post("/evaluation/refresh")
async def refresh():
    return await upstream("METADATA_INGEST_URL", "/internal/store/refresh", {})


@router.get("/api/v2/sessions/{session_id}")
async def history(session_id: str):
    return await upstream("CHAT_INTENT_URL", "/internal/store/sessions/" + session_id)

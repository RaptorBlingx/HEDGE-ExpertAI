"""Mock HEDGE-IoT App Store API — FastAPI routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from hedge_shared.models_v2 import AppMetadataV2
from hedge_shared.saref import app_to_jsonld

router = APIRouter()

_DATA_PATH = Path(__file__).parent / "data" / "apps-v2.json"
_apps: list[dict] = []


def _load_apps() -> list[dict]:
    global _apps
    if not _apps:
        with open(_DATA_PATH) as f:
            _apps = json.load(f)
    return _apps


@router.get("/api/apps")
def list_apps(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all apps with pagination."""
    apps = [
        AppMetadataV2.model_validate(app).to_legacy_dict()
        for app in _load_apps()
    ]
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": len(apps),
        "page": page,
        "page_size": page_size,
        "apps": apps[start:end],
    }


@router.get("/api/apps/search")
def search_apps(q: str = Query(..., min_length=1)):
    """Basic keyword search across title, description, and tags."""
    apps = [
        AppMetadataV2.model_validate(app).to_legacy_dict()
        for app in _load_apps()
    ]
    query_lower = q.lower()
    results = []
    for app in apps:
        text = f"{app['title']} {app['description']} {' '.join(app.get('tags', []))}".lower()
        if query_lower in text:
            results.append(app)
    return {"total": len(results), "query": q, "apps": results}


@router.get("/api/apps/{app_id}")
def get_app(app_id: str):
    """Get a single app by ID."""
    apps = [
        AppMetadataV2.model_validate(app).to_legacy_dict()
        for app in _load_apps()
    ]
    for app in apps:
        if app["id"] == app_id:
            return app
    raise HTTPException(status_code=404, detail=f"App {app_id} not found")


@router.get("/api/v2/apps")
def list_apps_v2(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List strict v2 synthetic catalogue records."""
    apps = _load_apps()
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "schema_version": "2.0",
        "total": len(apps),
        "page": page,
        "page_size": page_size,
        "apps": apps[start:end],
    }


@router.get("/api/v2/apps/{app_id}.jsonld")
def get_app_v2_jsonld(app_id: str):
    """Return a synthetic app as JSON-LD."""
    app = next((item for item in _load_apps() if item["id"] == app_id), None)
    if app is None:
        raise HTTPException(status_code=404, detail=f"App {app_id} not found")
    return JSONResponse(
        content=app_to_jsonld(AppMetadataV2.model_validate(app)),
        media_type="application/ld+json",
    )


@router.get("/api/v2/apps/{app_id}")
def get_app_v2(app_id: str):
    """Get a single strict v2 synthetic record."""
    app = next((item for item in _load_apps() if item["id"] == app_id), None)
    if app is None:
        raise HTTPException(status_code=404, detail=f"App {app_id} not found")
    return app


# Deterministic Ollama-compatible fixture used only by the Docker E2E profile.
@router.get("/api/tags", include_in_schema=False)
def deterministic_model_tags() -> dict:
    return {"models": [{"name": "deterministic-e2e"}]}


@router.post("/api/chat", include_in_schema=False)
def deterministic_model_chat(payload: Annotated[dict, Body()]):
    """Return fixed untrusted output so grounding fallback remains exercised."""
    content = "Deterministic fixture output; the application must validate or replace this."
    if not payload.get("stream"):
        return {
            "model": "deterministic-e2e",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "done_reason": "stop",
            "eval_count": 12,
        }

    async def stream():
        yield json.dumps(
            {
                "model": "deterministic-e2e",
                "message": {"role": "assistant", "content": content},
                "done": False,
            }
        ) + "\n"
        yield json.dumps(
            {
                "model": "deterministic-e2e",
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
                "eval_count": 12,
            }
        ) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")

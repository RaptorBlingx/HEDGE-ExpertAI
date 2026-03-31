"""Mock HEDGE-IoT App Store API — FastAPI routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_DATA_PATH = Path(__file__).parent / "data" / "apps.json"
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
    apps = _load_apps()
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
    apps = _load_apps()
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
    apps = _load_apps()
    for app in apps:
        if app["id"] == app_id:
            return app
    raise HTTPException(status_code=404, detail=f"App {app_id} not found")

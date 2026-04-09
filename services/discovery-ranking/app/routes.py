"""Discovery & Ranking — FastAPI routes.

IMPORTANT: /api/v1/apps/search MUST be defined BEFORE /api/v1/apps/{app_id}
to avoid FastAPI treating 'search' as an app_id.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .indexer import ensure_collection, get_app_by_id, get_client, index_batch
from .searcher import hybrid_search, invalidate_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    saref_class: str | None = None


class IndexRequest(BaseModel):
    apps: list[dict[str, Any]]


# SEARCH must come before {app_id} — fastapi route ordering
@router.post("/apps/search")
def search_apps(req: SearchRequest):
    """Hybrid search: vector + keyword + SAREF boost."""
    client = get_client()
    results = hybrid_search(
        client,
        query=req.query,
        top_k=req.top_k,
        saref_class=req.saref_class,
    )
    return {"query": req.query, "total": len(results), "results": results}


@router.post("/apps/index")
def index_apps(req: IndexRequest):
    """Index a batch of apps into the vector store."""
    client = get_client()
    ensure_collection(client)
    count = index_batch(client, req.apps)
    invalidate_cache()
    return {"indexed": count}


@router.get("/apps/{app_id}")
def get_app(app_id: str):
    """Retrieve a single app by ID from the index."""
    client = get_client()
    app = get_app_by_id(client, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail=f"App {app_id} not found in index")
    return app

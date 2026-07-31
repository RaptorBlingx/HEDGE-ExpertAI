"""Discovery & Ranking — FastAPI routes.

IMPORTANT: /api/v1/apps/search MUST be defined BEFORE /api/v1/apps/{app_id}
to avoid FastAPI treating 'search' as an app_id.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from hedge_shared.models_v2 import ReindexRequestV2, SearchRequestV2
from hedge_shared.saref import app_to_jsonld
from hedge_shared.storage import current_catalogue_revision, get_catalogue_app, list_catalogue_apps
from pydantic import BaseModel, Field

from .indexer import (
    apply_operations,
    ensure_collection,
    get_app_by_id,
    get_client,
    index_batch,
    promote_collection,
    rebuild_collection,
)
from .searcher import hybrid_search, invalidate_cache
from .searcher_v2 import search_apps_v2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    saref_class: str | None = None


class IndexRequest(BaseModel):
    apps: list[dict[str, Any]]


class IndexOperation(BaseModel):
    operation: Literal["upsert", "delete"]
    app_id: str = Field(min_length=3, max_length=100)
    revision: int = Field(ge=1)
    app: dict[str, Any] | None = None


class IndexOperationsRequest(BaseModel):
    operations: list[IndexOperation] = Field(min_length=1, max_length=100)


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


v2_router = APIRouter(prefix="/api/v2")


@v2_router.post("/apps/search")
def search_apps_v2_route(req: SearchRequestV2) -> dict[str, Any]:
    """Search independent lexical and dense rankings and fuse with RRF."""
    client = get_client()
    results = search_apps_v2(
        client,
        query=req.query,
        locale=req.locale,
        filters=req.filters,
        limit=req.limit,
        catalogue_revision=current_catalogue_revision(),
    )
    return {
        "schema_version": "2.0",
        "query": req.query,
        "locale": req.locale,
        "total": len(results),
        "next_cursor": None,
        "results": results,
    }


@v2_router.get("/catalog/apps")
def catalogue_apps(
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List authoritative active catalogue records."""
    if page < 1 or not 1 <= page_size <= 100:
        raise HTTPException(status_code=422, detail="Invalid pagination")
    total, apps = list_catalogue_apps(
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return {
        "schema_version": "2.0",
        "total": total,
        "page": page,
        "page_size": page_size,
        "apps": apps,
    }


@v2_router.post("/index/operations")
def index_operations(req: IndexOperationsRequest) -> dict[str, int]:
    """Apply internal, revisioned vector-index operations."""
    client = get_client()
    ensure_collection(client)
    payload = [operation.model_dump(mode="json") for operation in req.operations]
    if any(item["operation"] == "upsert" and item["app"] is None for item in payload):
        raise HTTPException(status_code=422, detail="upsert operations require app")
    applied = apply_operations(client, payload)
    invalidate_cache()
    return {"applied": applied}


@v2_router.post("/index/rebuild")
def reindex(req: ReindexRequestV2) -> dict[str, Any]:
    """Rebuild from PostgreSQL and atomically promote the validated alias."""
    client = get_client()
    try:
        result = rebuild_collection(client, req.collection_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    invalidate_cache()
    return result


@v2_router.post("/index/promote")
def promote_index(req: ReindexRequestV2) -> dict[str, Any]:
    """Atomically roll forward or back to a validated versioned collection."""
    client = get_client()
    try:
        result = promote_collection(client, req.collection_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    invalidate_cache()
    return result


@v2_router.get(
    "/catalog/apps/{app_id}.jsonld",
    response_model=None,
    responses={200: {"content": {"application/ld+json": {}}}},
)
def catalogue_app_jsonld(app_id: str):
    """Return the URI-level catalogue representation as JSON-LD."""
    from fastapi.responses import JSONResponse
    from hedge_shared.models_v2 import AppMetadataV2

    app = get_catalogue_app(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    return JSONResponse(
        content=app_to_jsonld(AppMetadataV2.model_validate(app)),
        media_type="application/ld+json",
    )


@v2_router.get("/catalog/apps/{app_id}")
def catalogue_app(app_id: str) -> dict[str, Any]:
    """Return an app from the authoritative PostgreSQL catalogue."""
    app = get_catalogue_app(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="App not found")
    return app

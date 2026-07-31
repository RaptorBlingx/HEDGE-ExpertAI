"""Expert Recommend — FastAPI routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from hedge_shared.models_v2 import Locale, SearchFilters
from pydantic import BaseModel, Field

from .recommender import (
    _sse,
    explain_app,
    recommend,
    recommend_stream,
    recommend_v2,
    recommend_v2_stream,
)

router = APIRouter(prefix="/api/v1")


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=10)
    saref_class: str | None = None


class ExplainRequest(BaseModel):
    query: str = Field(..., min_length=1)
    app: dict[str, Any]


class RecommendRequestV2(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    locale: Locale = "en"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    limit: int = Field(default=5, ge=1, le=10)


@router.post("/recommend")
def get_recommendations(req: RecommendRequest):
    """Full recommendation pipeline: search + LLM explanation."""
    result = recommend(
        query=req.query,
        top_k=req.top_k,
        saref_class=req.saref_class,
    )
    return result


@router.post("/recommend/stream")
async def stream_recommendations(req: RecommendRequest):
    """Streaming recommendation: search results + LLM explanation via SSE."""
    return StreamingResponse(
        recommend_stream(query=req.query, top_k=req.top_k, saref_class=req.saref_class),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/explain")
def get_explanation(req: ExplainRequest):
    """Explain why a specific app matches a query."""
    explanation = explain_app(query=req.query, app=req.app)
    return {"query": req.query, "app_title": req.app.get("title"), "explanation": explanation}


v2_router = APIRouter(prefix="/api/v2")


@v2_router.post("/recommend")
def get_recommendations_v2(req: RecommendRequestV2):
    """Validated multilingual recommendation response."""
    return recommend_v2(
        query=req.query,
        locale=req.locale,
        filters=req.filters.model_dump(mode="json"),
        limit=req.limit,
    )


@v2_router.post(
    "/recommend/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def stream_recommendations_v2(req: RecommendRequestV2):
    """SSE contract that only streams explanations after validation."""

    def generate():
        yield _sse({"type": "stage", "stage": "retrieval"})
        for event in recommend_v2_stream(
            query=req.query,
            locale=req.locale,
            filters=req.filters.model_dump(mode="json"),
            limit=req.limit,
        ):
            yield _sse(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

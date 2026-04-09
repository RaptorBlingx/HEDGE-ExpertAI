"""Expert Recommend — FastAPI routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .recommender import explain_app, recommend, recommend_stream

router = APIRouter(prefix="/api/v1")


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=10)
    saref_class: str | None = None


class ExplainRequest(BaseModel):
    query: str = Field(..., min_length=1)
    app: dict[str, Any]


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

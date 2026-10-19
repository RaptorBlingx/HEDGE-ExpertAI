"""Internal composition by the existing expert; no duplicate recommendation logic."""
from typing import Literal

from fastapi import APIRouter, Depends
from hedge_shared.private_store import require_internal_key
from pydantic import BaseModel, Field

from .recommender import _recommendation_decision, _recommendation_narrative
from .store_conversation import prepared_answer

router = APIRouter(prefix="/internal/store", dependencies=[Depends(require_internal_key)])


class Compose(BaseModel):
    mode: Literal["describe", "decide", "present"]
    question: str = Field(max_length=8000)
    rows: list[dict] = Field(default_factory=list, max_length=100)
    response: dict = Field(default_factory=dict)
    locale: str = "en"


@router.post("/compose")
def compose(req: Compose):
    if req.mode == "decide":
        return _recommendation_decision(req.question, req.rows, req.locale)
    if req.mode == "describe":
        return {"message": _recommendation_narrative(req.question, req.rows, req.locale)}
    message = prepared_answer(req.question, req.response, req.locale)
    return {"message": message, "context": req.response.get("context", {})}

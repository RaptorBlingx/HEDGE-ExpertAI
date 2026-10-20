"""Internal composition by the existing expert; no duplicate recommendation logic."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from hedge_shared.config import Settings
from hedge_shared.private_store import require_internal_key
from hedge_shared.store_language import search_language
from pydantic import BaseModel, Field

from .recommender import _recommendation_decision, _recommendation_narrative
from .store_conversation import prepared_answer
from .suitability import ReviewedSupport, source_digest

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


class Interpret(BaseModel):
    question: str = Field(max_length=8000)
    locale: str = "en"
    directory: list[dict] = Field(default_factory=list, max_length=100)
    context: dict = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list, max_length=20)


class Reason(BaseModel):
    question: str = Field(max_length=8000)
    locale: str = "en"
    action: Literal["browse", "search", "answer", "compare", "clarify", "chat"]
    rows: list[dict] = Field(default_factory=list, max_length=5)
    history: list[dict] = Field(default_factory=list, max_length=20)
    references: dict = Field(default_factory=dict)
    nlu: dict = Field(default_factory=dict)


def require_semantic():
    if not Settings().STORE_SEMANTIC_ENABLED:
        raise HTTPException(404, "Semantic recovery is disabled")


@router.post("/interpret", dependencies=[Depends(require_semantic)])
def interpret(req: Interpret):
    from .store_conversation import plan
    try:
        return plan(req.question, req.locale, req.directory, req.context, req.history)
    except Exception:
        # Validation errors can include model text. Keep it out of HTTP errors
        # and server tracebacks; the caller records an unavailable interpretation.
        raise HTTPException(503, "Store interpretation unavailable") from None


@router.post("/reason", dependencies=[Depends(require_semantic)])
def reason(req: Reason):
    from .store_conversation import respond
    answer = respond(req.question, req.rows, req.locale, req.action, req.history,
                     references=req.references, semantic=True, allow_repair=True, nlu_hint=req.nlu)
    if answer["generation"]["source"] != "ollama":
        return answer
    receipts = {row["app"]["id"]: ReviewedSupport(
                request=search_language(req.question, req.locale), app_id=row["app"]["id"],
                source_digest=source_digest(row["app"], req.locale),
                quotes=tuple((q["field"], q["quote"]) for q in answer.get("support", {}).get(str(row["rank"]), [])))
                for row in req.rows if str(row["rank"]) in answer.get("recommendations", [])}
    selected = [r for r in req.rows if r["app"]["id"] in receipts]
    # Reuse the single recommendation boundary. Explanations/browsing may show
    # context cards without asserting that an App meets a functional requirement.
    decision = _recommendation_decision(req.question, selected, req.locale, reviewed_support=receipts)
    answer["reviewed_rows"] = decision["apps"]
    if selected:
        answer["recommendation_decision"] = decision["decision"]
    elif req.action == "search" or answer["decision"] == "no_match":
        answer["recommendation_decision"] = {"outcome": "abstained", "reason": "semantic_evidence_insufficient"}
    answer["generation"]["reviewed_support"] = answer.get("support", {})
    return answer

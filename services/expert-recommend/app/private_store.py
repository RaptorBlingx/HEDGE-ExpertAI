"""Internal answers for the Store assistant; the recommendation boundary stays in the verifier.

Chat decides what is asked and about which Apps. These routes answer it from
current sources: verifier decisions, capability and search answers (with model
review of paraphrased matches when enabled), listings, explanations, and the
model's choice between two readings of a message.
"""
import json
import queue
import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from hedge_shared.config import Settings
from hedge_shared.private_store import require_internal_key
from pydantic import BaseModel, Field

from .answers import capability_answer, listing, search_answer, unverified
from .recommender import _recommendation_decision

router = APIRouter(prefix="/internal/store", dependencies=[Depends(require_internal_key)])


class Compose(BaseModel):
    mode: Literal["decide", "check", "review", "list", "unverified"]
    question: str = Field(default="", max_length=8000)
    rows: list[dict] = Field(default_factory=list, max_length=100)
    fields: list[str] = Field(default_factory=list, max_length=20)
    locale: str = "en"


@router.post("/compose")
def compose(req: Compose):
    if req.mode == "decide":
        return _recommendation_decision(req.question, req.rows, req.locale)
    if req.mode == "check":
        # Whether these Apps document the need, said as an answer to that question.
        return capability_answer(req.question, req.rows, req.locale)
    if req.mode == "review":
        # A search found no documented match; confirm paraphrased ones.
        return search_answer(req.question, req.rows, req.locale)
    if req.mode == "list":
        return {"message": listing([row["app"] for row in req.rows])}
    return {"message": unverified(req.fields)}


def require_semantic():
    if not Settings().STORE_SEMANTIC_ENABLED:
        raise HTTPException(404, "Model interpretation is disabled")


class Arbitrate(BaseModel):
    message: str = Field(max_length=2000)
    options: list[str] = Field(min_length=2, max_length=4)
    history: list[dict] = Field(default_factory=list, max_length=4)


@router.post("/arbitrate", dependencies=[Depends(require_semantic)])
def arbitrate(req: Arbitrate):
    """Which of two readings the user meant; a number, never facts or Apps."""
    from .interpretation import choose
    try:
        return {"choice": choose(req.message, [o[:300] for o in req.options], req.history)}
    except Exception:
        # Validation errors can include model text; keep it out of errors and logs.
        raise HTTPException(503, "Interpretation unavailable") from None


class Explain(BaseModel):
    act: str = Field(pattern=r"^(?:overview|simple|example|analogy|how|term|meaning|differently|compare|choose|"
                             r"audience|provider|price|access|details|ask|open)$")
    question: str = Field(max_length=2000)
    apps: list[dict] = Field(default_factory=list, max_length=5)
    state: dict = Field(default_factory=dict)
    history: list[dict] = Field(default_factory=list, max_length=20)
    phrase: str = Field(default="", max_length=120)
    stream: bool = False


@router.post("/explain")
def explain(req: Explain):
    """Conversational explanation; never a recommendation decision or new evidence.

    With stream=true the response is NDJSON: {"delta": ...} lines carrying
    checked model sentences as they are generated, then {"final": <answer>}.
    """
    from .explainer import respond as explain_apps
    if not req.stream:
        return explain_apps(req.act, req.question, req.apps, req.state, req.history, req.phrase)
    updates: queue.Queue = queue.Queue()

    def work():
        try:
            final = explain_apps(req.act, req.question, req.apps, req.state, req.history, req.phrase,
                                 on_delta=lambda text: updates.put({"delta": text}))
        except Exception:
            final = {"message": "", "error": "explanation_unavailable"}
        updates.put({"final": final})

    threading.Thread(target=work, daemon=True).start()

    def lines():
        while True:
            item = updates.get()
            yield json.dumps(item, ensure_ascii=False) + "\n"
            if "final" in item:
                return

    return StreamingResponse(lines(), media_type="application/x-ndjson")

"""Current, scoped private session hydration for widget history restoration."""
from fastapi import APIRouter, Depends, HTTPException
from hedge_shared.private_store import require_internal_key

from .private_store import resolve
from .session import get_session

router = APIRouter(prefix="/internal/store", dependencies=[Depends(require_internal_key)])


@router.get("/sessions/{session_id}")
def history(session_id: str):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session expired")
    context = session.get("context") or {}
    identities = context.get("displayed_ids", [r["app"]["id"] for r in context.get("last_results", [])])
    return {"messages": session.get("messages", []),
            "apps": [{"app": app, "rank": i + 1, "evidence_fields": ["reference"]}
                     for i, app in enumerate(resolve(identities))]}

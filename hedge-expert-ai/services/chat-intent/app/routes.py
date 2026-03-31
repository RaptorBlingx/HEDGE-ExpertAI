"""Chat Intent — FastAPI routes."""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .classifier import classify
from .session import delete_session, get_or_create_session, get_session, update_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

EXPERT_RECOMMEND_URL = os.getenv("EXPERT_RECOMMEND_URL", "http://expert-recommend:8002")
DISCOVERY_RANKING_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1)


GREETING_RESPONSE = (
    "Hello! I'm HEDGE-ExpertAI, your AI assistant for the HEDGE-IoT App Store. "
    "I can help you discover and understand IoT applications. "
    "Try asking me something like 'Find apps for energy monitoring' or "
    "'Show me smart building solutions'."
)

HELP_RESPONSE = (
    "I can help you with:\n"
    "- **Search for apps**: 'Find apps for energy monitoring'\n"
    "- **Get recommendations**: 'I need a solution for smart irrigation'\n"
    "- **Learn about an app**: 'Tell me about app-001'\n"
    "- **Explore categories**: 'Show me environmental monitoring apps'\n\n"
    "Just type your question and I'll find the best matching IoT applications!"
)


@router.post("/chat")
def chat(req: ChatRequest):
    """Main chat endpoint — classify intent, route, respond."""
    session_id, history = get_or_create_session(req.session_id)

    # Classify intent
    result = classify(req.message)
    intent = result.intent

    # Add user message to history
    history.append({"role": "user", "content": req.message})

    response_message = ""
    apps: list = []

    if intent == "greeting":
        response_message = GREETING_RESPONSE

    elif intent == "help":
        response_message = HELP_RESPONSE

    elif intent == "detail":
        app_id = result.entities.get("app_id")
        if app_id:
            response_message, apps = _handle_detail(req.message, app_id)
        else:
            # No app ID found, treat as search
            response_message, apps = _handle_search(req.message)

    elif intent in ("search", "unknown"):
        response_message, apps = _handle_search(req.message)

    # Add assistant response to history
    history.append({"role": "assistant", "content": response_message})

    # Keep history manageable (last 20 messages)
    if len(history) > 20:
        history = history[-20:]

    # Save context with last search results for follow-ups
    context = {}
    if apps:
        context["last_results"] = apps[:5]
    update_session(session_id, history, context)

    return {
        "session_id": session_id,
        "message": response_message,
        "intent": intent,
        "apps": apps,
    }


@router.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str):
    """Get session history."""
    data = get_session(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, **data}


@router.delete("/chat/sessions/{session_id}")
def end_chat_session(session_id: str):
    """End and delete a session."""
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


def _handle_search(query: str) -> tuple[str, list]:
    """Call expert-recommend for search + explanation."""
    try:
        resp = httpx.post(
            f"{EXPERT_RECOMMEND_URL}/api/v1/recommend",
            json={"query": query, "top_k": 5},
            timeout=180.0,  # LLM can be slow on CPU
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", ""), data.get("apps", [])
    except Exception:
        logger.exception("Expert-recommend call failed")
        return "I'm having trouble connecting to the recommendation service. Please try again.", []


def _handle_detail(query: str, app_id: str) -> tuple[str, list]:
    """Get app details and explain."""
    try:
        # Fetch app from discovery-ranking
        resp = httpx.get(
            f"{DISCOVERY_RANKING_URL}/api/v1/apps/{app_id}",
            timeout=30.0,
        )
        if resp.status_code == 404:
            return f"I couldn't find an app with ID '{app_id}'. It may not be indexed yet.", []
        resp.raise_for_status()
        app = resp.json()

        # Get LLM explanation
        explain_resp = httpx.post(
            f"{EXPERT_RECOMMEND_URL}/api/v1/explain",
            json={"query": query, "app": app},
            timeout=180.0,
        )
        explain_resp.raise_for_status()
        explanation = explain_resp.json().get("explanation", "")

        return explanation, [{"app": app, "score": 1.0}]
    except Exception:
        logger.exception("Detail handling failed")
        return "I had trouble looking up that app. Please try again.", []

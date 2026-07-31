"""Chat Intent — FastAPI routes."""

from __future__ import annotations

import logging
import os
import re
import uuid

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from hedge_shared.models_v2 import (
    ChatRequestV2,
    RecommendationEventRequest,
)
from hedge_shared.storage import (
    create_impression,
    recommendation_kpis,
    record_recommendation_event,
)
from pydantic import BaseModel, Field

from .classifier import classify
from .session import (
    delete_session,
    get_feedback_stats,
    get_or_create_session,
    get_session,
    get_session_feedback,
    get_session_log,
    list_recorded_sessions,
    log_session_event,
    record_feedback,
    update_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

EXPERT_RECOMMEND_URL = os.getenv("EXPERT_RECOMMEND_URL", "http://expert-recommend:8002")
DISCOVERY_RANKING_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., min_length=1, max_length=2000)
    locale: str = Field(default="en", pattern=r"^(en|de|fr|es|it|nl|pt|tr)$")


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
async def chat(req: ChatRequest):
    """Main chat endpoint — classify intent, route, respond."""
    session_id, history = get_or_create_session(req.session_id)

    # Log session start if new
    if not req.session_id:
        log_session_event(session_id, "start")

    # Classify intent
    result = classify(req.message)
    intent = result.intent

    # Add user message to history
    history.append({"role": "user", "content": req.message})
    log_session_event(session_id, "message", {"role": "user", "intent": intent})

    response_message = ""
    apps: list = []

    if intent == "greeting":
        response_message = GREETING_RESPONSE

    elif intent == "help":
        response_message = HELP_RESPONSE

    elif intent == "detail":
        app_id = result.entities.get("app_id")
        if app_id:
            response_message, apps = await _handle_detail_async(req.message, app_id)
        else:
            # No app ID found, treat as search
            response_message, apps = await _handle_search_async(req.message)

    elif intent in ("search", "unknown"):
        response_message, apps = await _handle_search_async(req.message)

    # Add assistant response to history
    history.append({"role": "assistant", "content": response_message})

    # Keep history manageable (last 20 messages)
    if len(history) > 20:
        history = history[-20:]

    # Save context with last search results for follow-ups
    context = {}
    if apps:
        context["last_results"] = apps[:5]
        app_ids = [a.get("app", {}).get("id", "") if isinstance(a, dict) else "" for a in apps[:5]]
        log_session_event(session_id, "recommendation", {"app_ids": app_ids, "count": len(apps)})
    update_session(session_id, history, context)

    return {
        "session_id": session_id,
        "message": response_message,
        "intent": intent,
        "apps": apps,
    }


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat endpoint — SSE with apps + LLM tokens."""
    import json as _json

    session_id, history = get_or_create_session(req.session_id)
    result = classify(req.message)
    intent = result.intent
    app_id = result.entities.get("app_id") if isinstance(result.entities, dict) else None
    history.append({"role": "user", "content": req.message})

    # For greeting/help, return static SSE response
    if intent in ("greeting", "help"):
        content = GREETING_RESPONSE if intent == "greeting" else HELP_RESPONSE

        async def _static():
            yield f"data: {_json.dumps({'type': 'token', 'content': content})}\n\n"
            history.append({"role": "assistant", "content": content})
            update_session(session_id, history[-20:], {})
            yield f"data: {_json.dumps({'type': 'done', 'session_id': session_id, 'intent': intent})}\n\n"

        return StreamingResponse(
            _static(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if intent == "detail" and app_id:
        async def _detail_stream():
            response_message, apps = await _handle_detail_async(req.message, app_id)
            if apps:
                yield f"data: {_json.dumps({'type': 'apps', 'apps': apps})}\n\n"
            yield f"data: {_json.dumps({'type': 'token', 'content': response_message})}\n\n"

            history.append({"role": "assistant", "content": response_message})
            context = {"last_results": apps[:5]} if apps else {}
            update_session(session_id, history[-20:], context)
            yield f"data: {_json.dumps({'type': 'done', 'session_id': session_id, 'intent': intent})}\n\n"

        return StreamingResponse(
            _detail_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # For search/detail intents, proxy stream from expert-recommend
    async def _proxy():
        full_text = ""
        apps = []
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{EXPERT_RECOMMEND_URL}/api/v1/recommend/stream",
                    json={"query": req.message, "top_k": 5},
                    timeout=180.0,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        try:
                            data = _json.loads(line[6:])
                        except (ValueError, KeyError):
                            data = {}
                        if data.get("type") == "apps":
                            apps = data.get("apps", [])
                        elif data.get("type") == "token":
                            full_text += data.get("content", "")
                        yield f"{line}\n\n"
        except Exception:
            logger.exception("Stream proxy failed")
            yield f"data: {_json.dumps({'type': 'token', 'content': 'I am having trouble connecting to the recommendation service. Please try again.'})}\n\n"

        # Update session after stream completes
        history.append({"role": "assistant", "content": full_text})
        context = {"last_results": apps[:5]} if apps else {}
        update_session(session_id, history[-20:], context)
        yield f"data: {_json.dumps({'type': 'done', 'session_id': session_id, 'intent': intent})}\n\n"

    return StreamingResponse(
        _proxy(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
    log_session_event(session_id, "end")
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


# ---------------------------------------------------------------------------
# Recommendation feedback (KPI: ≥ 70% session acceptance)
# ---------------------------------------------------------------------------
class FeedbackRequest(BaseModel):
    session_id: str
    app_id: str
    action: str = Field(..., pattern=r"^(click|accept|dismiss)$")
    rating: int | None = Field(None, ge=1, le=5)


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    """Record user feedback on a recommended app."""
    record_feedback(
        session_id=req.session_id,
        app_id=req.app_id,
        action=req.action,
        rating=req.rating,
    )
    log_session_event(req.session_id, "feedback", {"app_id": req.app_id, "action": req.action})
    return {"status": "recorded"}


@router.get("/feedback/stats")
def feedback_stats():
    """Aggregate feedback statistics for KPI reporting."""
    stats = get_feedback_stats()
    total_actions = stats["total_click"] + stats["total_accept"]
    total_all = total_actions + stats["total_dismiss"]
    stats["acceptance_rate"] = (
        round(total_actions / total_all, 4) if total_all > 0 else None
    )
    return stats


@router.get("/feedback/sessions/{session_id}")
def session_feedback(session_id: str):
    """Feedback entries for a specific session."""
    entries = get_session_feedback(session_id)
    return {"session_id": session_id, "feedback": entries}


# ---------------------------------------------------------------------------
# Session recording (Obj 5: ≥ 10 complete user-interaction sessions)
# ---------------------------------------------------------------------------

@router.get("/sessions/recorded")
def list_sessions(limit: int = 100):
    """List all recorded sessions with summary stats."""
    sessions = list_recorded_sessions(limit=limit)
    return {"total": len(sessions), "sessions": sessions}


@router.get("/sessions/recorded/{session_id}")
def get_recorded_session(session_id: str):
    """Get full event log for a recorded session."""
    events = get_session_log(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session log not found")
    return {"session_id": session_id, "events": events}


# ---------------------------------------------------------------------------
# Version 2 conversational and telemetry contracts
# ---------------------------------------------------------------------------

v2_router = APIRouter(prefix="/api/v2")

_ORDINALS = {
    "first": 0,
    "1": 0,
    "second": 1,
    "2": 1,
    "third": 2,
    "3": 2,
    "fourth": 3,
    "4": 3,
    "fifth": 4,
    "5": 4,
    "erste": 0,
    "zweite": 1,
    "premier": 0,
    "deuxième": 1,
    "primero": 0,
    "segundo": 1,
    "ilk": 0,
    "ikinci": 1,
}

_STATIC = {
    "greeting": {
        "en": "Hello! I can help you find and compare IoT applications.",
        "de": "Hallo! Ich kann Ihnen helfen, IoT-Anwendungen zu finden und zu vergleichen.",
        "fr": "Bonjour ! Je peux vous aider à trouver et comparer des applications IoT.",
        "es": "¡Hola! Puedo ayudarle a encontrar y comparar aplicaciones IoT.",
        "it": "Ciao! Posso aiutarti a trovare e confrontare applicazioni IoT.",
        "nl": "Hallo! Ik kan u helpen IoT-apps te vinden en te vergelijken.",
        "pt": "Olá! Posso ajudar a encontrar e comparar aplicações IoT.",
        "tr": "Merhaba! IoT uygulamalarını bulmanıza ve karşılaştırmanıza yardımcı olabilirim.",
    },
    "help": {
        "en": "Describe your use case, refine the results, ask about an app, or compare recent matches.",
        "de": "Beschreiben Sie den Anwendungsfall, verfeinern Sie Treffer oder vergleichen Sie Apps.",
        "fr": "Décrivez votre cas d'usage, affinez les résultats ou comparez des applications.",
        "es": "Describa su caso de uso, refine los resultados o compare aplicaciones.",
        "it": "Descrivi il caso d'uso, affina i risultati o confronta le applicazioni.",
        "nl": "Beschrijf uw gebruikssituatie, verfijn resultaten of vergelijk apps.",
        "pt": "Descreva o caso de uso, refine os resultados ou compare aplicações.",
        "tr": "Kullanım durumunuzu açıklayın, sonuçları daraltın veya uygulamaları karşılaştırın.",
    },
    "out_of_scope": {
        "en": "I can only help with discovery and explanation of IoT catalogue applications.",
        "de": "Ich unterstütze nur die Suche und Erklärung von IoT-Kataloganwendungen.",
        "fr": "Je peux uniquement aider à découvrir et expliquer les applications du catalogue IoT.",
        "es": "Solo puedo ayudar a descubrir y explicar aplicaciones del catálogo IoT.",
        "it": "Posso aiutare solo con le applicazioni del catalogo IoT.",
        "nl": "Ik kan alleen helpen met apps uit de IoT-catalogus.",
        "pt": "Só posso ajudar com aplicações do catálogo IoT.",
        "tr": "Yalnızca IoT kataloğu uygulamalarını bulma ve açıklama konusunda yardımcı olabilirim.",
    },
    "reset": {
        "en": "The previous search context has been cleared.",
        "de": "Der vorherige Suchkontext wurde gelöscht.",
        "fr": "Le contexte de recherche précédent a été effacé.",
        "es": "Se ha borrado el contexto de búsqueda anterior.",
        "it": "Il contesto di ricerca precedente è stato cancellato.",
        "nl": "De vorige zoekcontext is gewist.",
        "pt": "O contexto de pesquisa anterior foi limpo.",
        "tr": "Önceki arama bağlamı temizlendi.",
    },
}


def _static_message(intent: str, locale: str) -> str:
    translations = _STATIC[intent]
    return translations.get(locale, translations["en"])


def _context_for(session_id: str) -> dict:
    session = get_session(session_id) or {}
    return dict(session.get("context") or {})


def _referenced_result(message: str, context: dict) -> dict | None:
    lowered = message.casefold()
    for token, index in _ORDINALS.items():
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            results = context.get("last_results") or []
            if index < len(results):
                return results[index]
    return None


def _dialogue_query(message: str, intent: str, context: dict) -> str:
    if intent == "refine" and context.get("last_query"):
        return f"{context['last_query']} ; refinement: {message}"
    if intent == "compare" and context.get("last_results"):
        titles = []
        for item in context["last_results"][:3]:
            app = item.get("app", item)
            value = app.get("title", "")
            titles.append(value.get("en", "") if isinstance(value, dict) else str(value))
        return f"Compare {'; '.join(titles)} for: {message}"
    return message


def _dialogue_filters(req: ChatRequestV2, intent: str, context: dict) -> dict:
    """Merge explicit refinements while making a new search a clean topic."""
    incoming = req.filters.model_dump(mode="json")
    if intent not in {"refine", "compare", "detail"}:
        return incoming
    merged = dict(context.get("filters") or {})
    for key, value in incoming.items():
        if value not in (None, [], ""):
            merged[key] = value
    return merged


async def _recommend_v2(
    *,
    query: str,
    locale: str,
    filters: dict,
) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{EXPERT_RECOMMEND_URL}/api/v2/recommend",
            json={
                "query": query,
                "locale": locale,
                "filters": filters,
                "limit": 5,
            },
            timeout=180.0,
        )
    response.raise_for_status()
    return response.json()


@v2_router.post("/chat")
async def chat_v2(req: ChatRequestV2) -> dict:
    """Deterministic application-owned dialogue with durable impressions."""
    session_id, history = get_or_create_session(req.session_id)
    context = _context_for(session_id)
    result = classify(req.message)
    intent = result.intent

    if not req.session_id:
        log_session_event(session_id, "start", {"locale": req.locale})
    log_session_event(session_id, "message", {"role": "user", "intent": intent})

    if intent == "reset":
        delete_session(session_id)
        session_id, history = get_or_create_session(None)
        log_session_event(session_id, "start", {"locale": req.locale, "reset": True})
        message = _static_message("reset", req.locale)
        history.append({"role": "assistant", "content": message})
        update_session(session_id, history, {"locale": req.locale, "turn": 0})
        return {
            "schema_version": "2.0",
            "session_id": session_id,
            "intent": intent,
            "message": message,
            "apps": [],
            "impression_id": None,
        }

    if intent in {"greeting", "help", "out_of_scope"}:
        message = _static_message(intent, req.locale)
        apps: list[dict] = []
        timings: dict = {}
    else:
        filters = _dialogue_filters(req, intent, context)
        extension_uri = result.entities.get("extension_uri")
        if extension_uri and not filters.get("extension_uri"):
            filters["extension_uri"] = extension_uri
        referenced = _referenced_result(req.message, context)
        if intent == "detail" and referenced:
            app = referenced.get("app", referenced)
            filters["semantic_uri"] = None
            query = f"Explain application {app.get('id')}: {req.message}"
        else:
            query = _dialogue_query(req.message, intent, context)
        recommendation = await _recommend_v2(
            query=query,
            locale=req.locale,
            filters=filters,
        )
        message = recommendation.get("message", "")
        apps = recommendation.get("apps", [])
        timings = recommendation.get("timings", {})

    impression_id = None
    if apps:
        app_ids = [item.get("app", item).get("id", "") for item in apps]
        impression_id = create_impression(
            session_id=session_id,
            result_ids=[app_id for app_id in app_ids if app_id],
            locale=req.locale,
            intent=intent,
            timings=timings,
        )
        log_session_event(
            session_id,
            "recommendation",
            {"impression_id": impression_id, "count": len(apps)},
        )

    history.extend(
        [
            {"role": "user", "content": req.message},
            {"role": "assistant", "content": message},
        ]
    )
    context_update = {
        "locale": req.locale,
        "intent": intent,
        "filters": filters if intent not in {"greeting", "help", "out_of_scope"} else {},
        "last_query": req.message,
        "turn": int(context.get("turn", 0)) + 1,
    }
    if apps:
        context_update["last_results"] = apps[:5]
        context_update["last_impression_id"] = impression_id
    update_session(session_id, history[-20:], context_update)
    return {
        "schema_version": "2.0",
        "session_id": session_id,
        "intent": intent,
        "message": message,
        "apps": apps,
        "impression_id": impression_id,
        "timings": timings,
    }


def _sse_v2(event_id: str, data: dict) -> str:
    import json

    return f"id: {event_id}\nevent: {data['type']}\ndata: {json.dumps(data)}\n\n"


@v2_router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat_stream_v2(req: ChatRequestV2):
    """Versioned SSE with early ranked results and validated explanation text."""

    async def generate():
        import json

        request_id = str(uuid.uuid4())
        session_id, history = get_or_create_session(req.session_id)
        context = _context_for(session_id)
        classified = classify(req.message)
        intent = classified.intent
        sequence = 1

        def event(payload: dict) -> str:
            nonlocal sequence
            payload.update(
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "locale": req.locale,
                }
            )
            rendered = _sse_v2(f"{request_id}:{sequence}", payload)
            sequence += 1
            return rendered

        yield _sse_v2(
            f"{request_id}:{sequence}",
            {
                "type": "stage",
                "stage": "intent",
                "request_id": request_id,
                "session_id": session_id,
                "locale": req.locale,
            },
        )
        sequence += 1

        if intent in {"greeting", "help", "out_of_scope", "reset"}:
            try:
                response = await chat_v2(req)
                session_id = response["session_id"]
            except Exception:
                logger.exception("Static v2 dialogue failed")
                yield event(
                    {
                        "type": "problem",
                        "title": "Dialogue service unavailable",
                        "status": 503,
                    }
                )
                return
            yield event(
                {
                    "type": "explanation_delta",
                    "content": response["message"],
                }
            )
            yield event(
                {
                    "type": "complete",
                    "impression_id": None,
                    "intent": intent,
                    "timings": {},
                }
            )
            return

        if not req.session_id:
            log_session_event(session_id, "start", {"locale": req.locale})
        log_session_event(session_id, "message", {"role": "user", "intent": intent})
        filters = _dialogue_filters(req, intent, context)
        extension_uri = classified.entities.get("extension_uri")
        if extension_uri and not filters.get("extension_uri"):
            filters["extension_uri"] = extension_uri
        referenced = _referenced_result(req.message, context)
        if intent == "detail" and referenced:
            app = referenced.get("app", referenced)
            query = f"Explain application {app.get('id')}: {req.message}"
        else:
            query = _dialogue_query(req.message, intent, context)

        yield event({"type": "stage", "stage": "retrieval"})
        apps: list[dict] = []
        full_text = ""
        timings: dict = {}
        impression_id = None
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{EXPERT_RECOMMEND_URL}/api/v2/recommend/stream",
                    json={
                        "query": query,
                        "locale": req.locale,
                        "filters": filters,
                        "limit": 5,
                    },
                    timeout=180.0,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            upstream = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        upstream_type = upstream.get("type")
                        if upstream_type == "recommendations":
                            apps = upstream.get("apps", [])
                            timings.update(upstream.get("timings", {}))
                            if apps:
                                app_ids = [item.get("app", item).get("id") for item in apps]
                                impression_id = create_impression(
                                    session_id=session_id,
                                    result_ids=[app_id for app_id in app_ids if app_id],
                                    locale=req.locale,
                                    intent=intent,
                                    timings=timings,
                                )
                            yield event({"type": "stage", "stage": "ranking"})
                            yield event(
                                {
                                    "type": "recommendations",
                                    "apps": apps,
                                    "impression_id": impression_id,
                                    "timings": timings,
                                }
                            )
                        elif upstream_type == "stage":
                            yield event({"type": "stage", "stage": upstream.get("stage")})
                        elif upstream_type == "explanation_delta":
                            content = str(upstream.get("content", ""))
                            full_text += content
                            yield event({"type": "explanation_delta", "content": content})
                        elif upstream_type == "complete":
                            timings.update(upstream.get("timings", {}))
        except Exception:
            logger.exception("V2 streaming dialogue failed")
            yield event(
                {
                    "type": "problem",
                    "title": "Recommendation service unavailable",
                    "status": 503,
                }
            )
            return

        history.extend(
            [
                {"role": "user", "content": req.message},
                {"role": "assistant", "content": full_text},
            ]
        )
        context_update = {
            "locale": req.locale,
            "intent": intent,
            "filters": filters,
            "last_query": req.message,
            "turn": int(context.get("turn", 0)) + 1,
        }
        if apps:
            context_update["last_results"] = apps[:5]
            context_update["last_impression_id"] = impression_id
            log_session_event(
                session_id,
                "recommendation",
                {"impression_id": impression_id, "count": len(apps)},
            )
        update_session(session_id, history[-20:], context_update)
        yield event(
            {
                "type": "complete",
                "impression_id": impression_id,
                "intent": intent,
                "timings": timings,
            }
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@v2_router.post("/recommendation-events", status_code=201)
def submit_recommendation_event(req: RecommendationEventRequest) -> dict:
    """Record a verified, idempotent recommendation event."""
    try:
        created = record_recommendation_event(req)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "recorded" if created else "duplicate", "created": created}


@v2_router.get("/analytics/recommendations")
def recommendation_analytics() -> dict:
    """Durable session-level recommendation KPIs."""
    return recommendation_kpis()


@v2_router.delete("/sessions/{session_id}")
def delete_session_v2(session_id: str) -> dict:
    """End and erase operational session state."""
    log_session_event(session_id, "end")
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


async def _handle_search_async(query: str) -> tuple[str, list]:
    """Call expert-recommend for search + explanation (async)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{EXPERT_RECOMMEND_URL}/api/v1/recommend",
                json={"query": query, "top_k": 5},
                timeout=180.0,
            )
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", ""), data.get("apps", [])
    except Exception:
        logger.exception("Expert-recommend call failed")
        return "I'm having trouble connecting to the recommendation service. Please try again.", []


async def _handle_detail_async(query: str, app_id: str) -> tuple[str, list]:
    """Get app details and explain (async)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{DISCOVERY_RANKING_URL}/api/v1/apps/{app_id}",
                timeout=30.0,
            )
            if resp.status_code == 404:
                return f"I couldn't find an app with ID '{app_id}'. It may not be indexed yet.", []
            resp.raise_for_status()
            app = resp.json()

            explain_resp = await client.post(
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

"""Loopback-only manual evaluation adapter for the isolated Store playground."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from hedge_shared.models_v2 import ChatRequestV2

from scripts.store_v1_playground import ROOT, offline_playground


def create_app(playground):
    app = FastAPI(title="Isolated Store evaluation", docs_url=None, redoc_url=None, openapi_url=None)
    # A single evaluation process serializes turns, including streams. This
    # avoids lost Valkey updates without adding a production locking subsystem.
    turn_lock = asyncio.Lock()

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"detail": "Loopback evaluation only"}, status_code=403)
        origin = request.headers.get("origin")
        if request.method != "GET" and origin and origin != f"http://{request.headers['host']}":
            return JSONResponse({"detail": "Same-origin evaluation only"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        )
        return response

    @app.get("/api/v2/status")
    def status():
        import os

        return {"source": getattr(playground, "source", "authored-fixtures"),
                "catalogue": ("Authored sanitized evaluation fixtures; not live HEDGE data"
                              if getattr(playground, "source", "authored-fixtures") == "authored-fixtures"
                              else "Private Store snapshot; potentially incomplete, no ongoing Store access"),
                "snapshot_complete": False,
                "embeddings": "real pinned E5" if os.getenv("STORE_PLAYGROUND_E5") == "true" else "unavailable; lexical fallback",
                "intent": "real Rasa with confidence/health regex fallback" if os.getenv("RASA_ENABLED") == "true" else "regex fallback; Rasa unavailable",
                "generation": "Ollama enabled; validated excerpts or deterministic fallback per turn" if os.getenv("STORE_PLAYGROUND_OLLAMA") == "true" else "Deterministic source quotations; Ollama not used",
                "simulation_controls": callable(getattr(playground, "simulate", None)),
                "pipeline": getattr(playground, "pipeline", {}),
                "records": playground.records}

    @app.post("/evaluation/scenario/{action}")
    async def scenario(action: str):
        simulate = getattr(playground, "simulate", None)
        if not simulate or action not in {"update", "withdraw", "restore"}:
            raise HTTPException(status_code=404, detail="Authored scenario unavailable")
        async with turn_lock:
            return await asyncio.to_thread(simulate, action)

    @app.post("/api/v2/chat")
    async def chat(request: ChatRequestV2):
        async with turn_lock:
            try:
                return await playground.converse(request)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=503, detail="Offline retrieval unavailable") from None

    @app.get("/api/v2/sessions/{session_id}")
    async def history(session_id: str):
        async with turn_lock:
            session = playground.chat.get_session(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Evaluation session expired")
            identities = [r["app"]["id"] for r in (session.get("context") or {}).get("last_results", [])]
            apps = [{"app": app, "rank": i + 1, "evidence_fields": ["reference"]}
                    for i, app in enumerate(playground.policy.resolve(identities))]
            return {"messages": session.get("messages", []), "apps": apps}

    @app.post("/api/v2/chat/stream")
    async def stream(request: ChatRequestV2):
        async def events():
            async with turn_lock:
                yield 'data: {"type":"stage","stage":"retrieval"}\n\n'
                try:
                    result = await playground.converse(request)
                except Exception:
                    yield 'data: {"type":"problem","title":"Offline retrieval unavailable","status":503}\n\n'
                    return
                # Buffer the completed, source-validated response before delivery;
                # never stream unvalidated model tokens.
                payloads = [
                    {"type": "recommendations", "apps": result["apps"],
                     "impression_id": result["impression_id"]},
                    {"type": "stage", "stage": "explanation"},
                    {"type": "explanation_delta", "content": result["message"]},
                    {"type": "complete", "session_id": result["session_id"],
                     "intent": result["intent"], "nlu": result.get("nlu"), "generation": result.get("generation"), "impression_id": result["impression_id"]},
                ]
                for payload in payloads:
                    yield "data: " + json.dumps(payload) + "\n\n"

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    app.add_api_route("/api/v2/sessions/{session_id}", playground.chat.delete_session_v2, methods=["DELETE"])
    app.add_api_route("/api/v2/recommendation-events", playground.chat.submit_recommendation_event, methods=["POST"])

    @app.get("/")
    def index():
        return FileResponse(ROOT / "scripts/offline-store/index.html")

    # Serve only these public artifacts, never the repository or private samples.
    app.mount("/widget", StaticFiles(directory=ROOT / "frontend/widget"))
    app.mount("/evaluation", StaticFiles(directory=ROOT / "scripts/offline-store"))
    return app


@asynccontextmanager
async def lifespan(app):
    with offline_playground() as playground:
        # Mount after initialization; no catalogue bootstrap from requests.
        app.mount("/", create_app(playground))
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

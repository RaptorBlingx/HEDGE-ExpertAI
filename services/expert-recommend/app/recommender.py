"""Recommendation orchestrator — query → search → explain."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import httpx

from .llm_client import OllamaClient
from .prompts import build_explanation_messages, build_recommendation_messages

logger = logging.getLogger(__name__)

DISCOVERY_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")


def _first_sentence(text: str) -> str:
    """Return first sentence-like chunk for compact summaries."""
    cleaned = text.strip()
    if not cleaned:
        return "No description available."
    for separator in (".", "!", "?"):
        if separator in cleaned:
            prefix = cleaned.split(separator, 1)[0].strip()
            if prefix:
                return f"{prefix}{separator}"
    return cleaned


def _build_ranked_fallback(results: list[dict[str, Any]]) -> str:
    """Build deterministic ranking-consistent explanation when LLM output is contradictory."""
    lines = ["Based on your query, here are the ranked matches:"]

    for idx, result in enumerate(results, start=1):
        app = result.get("app", result)
        title = app.get("title", "Unknown app")
        reason = _first_sentence(app.get("description", ""))
        lines.append(f"{idx}. **{title}** — {reason}")

    top_title = (results[0].get("app", results[0]) if results else {}).get("title", "this app")
    lines.append("")
    lines.append(
        f"Recommendation: Start with **{top_title}** because it is the highest-ranked match from search results."
    )

    return "\n".join(lines)


def _is_ranking_consistent(explanation: str, results: list[dict[str, Any]]) -> bool:
    """Check that top/best/start-with statements align with ranked App 1."""
    if not explanation or not results:
        return True

    top_title = (results[0].get("app", results[0]) if results else {}).get("title", "").strip()
    if not top_title:
        return True

    lowered = explanation.lower()
    top_lower = top_title.lower()

    # If there are no ranking claims, keep the answer.
    if not re.search(r"\b(top|best|start with|recommendation)\b", lowered):
        return True

    # Ranking claims should mention App 1 near claim phrases.
    for match in re.finditer(r"\b(top|best|start with|recommendation)\b", lowered):
        start = max(0, match.start() - 200)
        end = match.end() + 200
        window = lowered[start:end]
        if top_lower not in window:
            return False

    return True


def _ensure_ranking_consistency(explanation: str, results: list[dict[str, Any]]) -> str:
    """Return explanation only if ranking claims align with returned ordering."""
    if _is_ranking_consistent(explanation, results):
        return explanation
    logger.warning("LLM recommendation narrative contradicted ranked order; using deterministic fallback")
    return _build_ranked_fallback(results)


def _search_apps(query: str, top_k: int = 5, saref_class: str | None = None) -> list[dict[str, Any]]:
    """Call discovery-ranking service for search results."""
    payload = {"query": query, "top_k": top_k}
    if saref_class:
        payload["saref_class"] = saref_class
    try:
        resp = httpx.post(
            f"{DISCOVERY_URL}/api/v1/apps/search",
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception:
        logger.exception("Failed to search apps")
        return []


def recommend(
    query: str,
    top_k: int = 5,
    saref_class: str | None = None,
) -> dict[str, Any]:
    """Full recommendation pipeline: search → LLM explain."""
    # 1. Search
    start = time.monotonic()
    results = _search_apps(query, top_k=top_k, saref_class=saref_class)
    search_elapsed = time.monotonic() - start
    logger.info("Search completed in %.2fs (%d results)", search_elapsed, len(results))

    if not results:
        return {
            "message": "I couldn't find any apps matching your query. Could you try rephrasing or being more specific?",
            "apps": [],
        }

    # 2. LLM explanation
    llm = OllamaClient()
    messages = build_recommendation_messages(query, results)

    try:
        explanation = llm.chat(messages)
    except Exception:
        logger.exception("LLM generation failed, returning results without explanation")
        explanation = "Here are the most relevant apps I found for your query."

    llm_elapsed = time.monotonic() - start - search_elapsed
    logger.info("LLM generation in %.1fs, total %.1fs", llm_elapsed, time.monotonic() - start)

    explanation = _ensure_ranking_consistency(explanation, results)

    return {
        "message": explanation,
        "apps": results,
    }


def explain_app(query: str, app: dict[str, Any]) -> str:
    """Generate an explanation for a single app."""
    llm = OllamaClient()
    messages = build_explanation_messages(query, app)
    try:
        return llm.chat(messages)
    except Exception:
        logger.exception("LLM explanation failed")
        return f"{app.get('title', 'This app')} may be relevant to your query."


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


def recommend_stream(
    query: str,
    top_k: int = 5,
    saref_class: str | None = None,
):
    """Streaming recommendation: search → apps event → stream LLM tokens."""
    start = time.monotonic()
    results = _search_apps(query, top_k=top_k, saref_class=saref_class)
    search_elapsed = time.monotonic() - start
    logger.info("Search completed in %.2fs (%d results)", search_elapsed, len(results))

    if not results:
        yield _sse({"type": "message", "content": "I couldn't find any apps matching your query. Could you try rephrasing or being more specific?"})
        yield _sse({"type": "done", "apps": []})
        return

    # Send apps immediately so the client can render cards
    yield _sse({"type": "apps", "apps": results})

    # Stream LLM explanation
    llm = OllamaClient()
    messages = build_recommendation_messages(query, results)

    try:
        for chunk in llm.chat_stream(messages):
            yield _sse({"type": "token", "content": chunk})
    except Exception:
        logger.exception("LLM streaming failed")
        yield _sse({"type": "token", "content": "Here are the most relevant apps I found for your query."})

    elapsed = time.monotonic() - start
    logger.info("Streaming recommendation completed in %.1fs", elapsed)
    yield _sse({"type": "done"})

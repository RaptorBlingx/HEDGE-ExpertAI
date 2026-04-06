"""Recommendation orchestrator — query → search → explain."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .llm_client import OllamaClient
from .prompts import build_explanation_messages, build_recommendation_messages

logger = logging.getLogger(__name__)

DISCOVERY_URL = os.getenv("DISCOVERY_RANKING_URL", "http://discovery-ranking:8003")


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
    results = _search_apps(query, top_k=top_k, saref_class=saref_class)

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

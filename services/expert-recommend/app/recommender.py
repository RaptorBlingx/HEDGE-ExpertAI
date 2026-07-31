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

LOCALIZED_INTROS = {
    "en": "Start with **{title}** because it is the highest-ranked evidence-backed match.",
    "de": "Beginnen Sie mit **{title}**, da dies der bestplatzierte, belegte Treffer ist.",
    "fr": "Commencez par **{title}**, le résultat étayé le mieux classé.",
    "es": "Empiece con **{title}**, el resultado fundamentado mejor clasificado.",
    "it": "Inizia con **{title}**, il risultato documentato con il ranking più alto.",
    "nl": "Begin met **{title}**, de hoogst gerangschikte onderbouwde match.",
    "pt": "Comece com **{title}**, o resultado fundamentado mais bem classificado.",
    "tr": "En yüksek sıralı ve kanıta dayalı eşleşme olan **{title}** ile başlayın.",
}


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


def _title(app: dict[str, Any], locale: str = "en") -> str:
    value = app.get("title", "Unknown app")
    if isinstance(value, dict):
        return str(value.get(locale) or value.get("en") or "Unknown app")
    return str(value)


def _build_ranked_fallback(
    results: list[dict[str, Any]],
    locale: str = "en",
) -> str:
    """Build deterministic ranking-consistent explanation when LLM output is contradictory."""
    top_app = results[0].get("app", results[0]) if results else {}
    top_title = _title(top_app, locale)
    lines = [
        LOCALIZED_INTROS.get(locale, LOCALIZED_INTROS["en"]).format(title=top_title),
        "",
    ]

    for idx, result in enumerate(results, start=1):
        app = result.get("app", result)
        title = _title(app, locale)
        reason = _first_sentence(app.get("description", ""))
        lines.append(f"- **App {idx}: {title}** — {reason}")

    return "\n".join(lines)


def _is_ranking_consistent(explanation: str, results: list[dict[str, Any]]) -> bool:
    """Check that top/best/start-with statements align with ranked App 1."""
    if not explanation or not results:
        return True

    top_title = _title(results[0].get("app", results[0]), "en").strip()
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


def _ensure_ranking_consistency(
    explanation: str,
    results: list[dict[str, Any]],
    locale: str = "en",
) -> str:
    """Return explanation only if ranking claims align with returned ordering."""
    if _is_ranking_consistent(explanation, results):
        return explanation
    logger.warning("LLM recommendation narrative contradicted ranked order; using deterministic fallback")
    return _build_ranked_fallback(results, locale)


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


def _search_apps_v2(
    query: str,
    *,
    locale: str,
    filters: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    try:
        response = httpx.post(
            f"{DISCOVERY_URL}/api/v2/apps/search",
            json={
                "query": query,
                "locale": locale,
                "filters": filters,
                "limit": limit,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception:
        logger.exception("Failed to search v2 catalogue")
        return []


def _evidence_explanations(
    results: list[dict[str, Any]],
    locale: str,
) -> list[dict[str, Any]]:
    explanations = []
    for result in results:
        app = result.get("app", result)
        summary = app.get("summary") or {}
        localized_summary = (
            summary.get(locale) or summary.get("en")
            if isinstance(summary, dict)
            else summary
        )
        explanations.append(
            {
                "app_id": app.get("id"),
                "text": localized_summary or _first_sentence(app.get("description", "")),
                "evidence_fields": [
                    "summary",
                    "capabilities",
                    "semantic_annotations",
                ],
            }
        )
    return explanations


def _all_results_mentioned_in_order(
    explanation: str,
    results: list[dict[str, Any]],
    locale: str,
) -> bool:
    """Require every returned app title to appear in retrieval order."""
    cursor = -1
    lowered = explanation.casefold()
    for result in results:
        title = _title(result.get("app", result), locale).casefold()
        position = lowered.find(title, cursor + 1)
        if position < 0:
            return False
        cursor = position
    return True


def recommend_v2(
    *,
    query: str,
    locale: str,
    filters: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    """Run v2 retrieval and emit validated, field-grounded explanations."""
    start = time.monotonic()
    results = _search_apps_v2(
        query,
        locale=locale,
        filters=filters,
        limit=limit,
    )
    search_elapsed = time.monotonic() - start
    if not results:
        return {
            "message": "No supported catalogue match was found.",
            "apps": [],
            "explanations": [],
            "timings": {"search_seconds": search_elapsed},
        }

    messages = build_recommendation_messages(query, results, locale=locale)
    try:
        generated = OllamaClient().chat(messages)
    except Exception:
        logger.exception("V2 LLM generation failed")
        generated = ""

    if not (
        generated
        and _is_ranking_consistent(generated, results)
        and _all_results_mentioned_in_order(generated, results, locale)
    ):
        generated = _build_ranked_fallback(results, locale)

    return {
        "message": generated,
        "apps": results,
        "explanations": _evidence_explanations(results, locale),
        "timings": {
            "search_seconds": search_elapsed,
            "complete_seconds": time.monotonic() - start,
        },
    }


def recommend_v2_stream(
    *,
    query: str,
    locale: str,
    filters: dict[str, Any],
    limit: int,
):
    """Retrieve first, then validate the complete narrative before streaming it.

    This provides a useful recommendation as soon as retrieval finishes while
    preserving the rule that no unvalidated model output reaches a client.
    """
    start = time.monotonic()
    results = _search_apps_v2(query, locale=locale, filters=filters, limit=limit)
    search_elapsed = time.monotonic() - start
    yield {
        "type": "recommendations",
        "apps": results,
        "timings": {"search_seconds": search_elapsed},
    }
    yield {"type": "stage", "stage": "explanation"}

    if not results:
        generated = "No supported catalogue match was found."
    else:
        messages = build_recommendation_messages(query, results, locale=locale)
        try:
            generated = OllamaClient().chat(messages)
        except Exception:
            logger.exception("V2 LLM generation failed")
            generated = ""
        if not (
            generated
            and _is_ranking_consistent(generated, results)
            and _all_results_mentioned_in_order(generated, results, locale)
        ):
            generated = _build_ranked_fallback(results, locale)

    for offset in range(0, len(generated), 120):
        yield {
            "type": "explanation_delta",
            "content": generated[offset : offset + 120],
        }
    yield {
        "type": "complete",
        "explanations": _evidence_explanations(results, locale),
        "timings": {
            "search_seconds": search_elapsed,
            "complete_seconds": time.monotonic() - start,
        },
    }


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
        yield _sse({"type": "token", "content": "I couldn't find any apps matching your query. Could you try rephrasing or being more specific?"})
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

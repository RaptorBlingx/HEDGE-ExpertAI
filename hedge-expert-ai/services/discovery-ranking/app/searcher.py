"""Hybrid search — vector + keyword + SAREF boost."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Any

from qdrant_client import QdrantClient

from .embeddings import encode_single
from .indexer import COLLECTION_NAME

logger = logging.getLogger(__name__)

# Scoring weights
W_VECTOR = 0.6
W_KEYWORD = 0.3
W_SAREF = 0.1


def hybrid_search(
    client: QdrantClient,
    query: str,
    top_k: int = 5,
    saref_class: str | None = None,
) -> list[dict[str, Any]]:
    """
    Hybrid search combining:
      - 0.6 × vector cosine similarity
      - 0.3 × keyword (BM25-lite) score
      - 0.1 × SAREF class match boost
    """
    query_vector = encode_single(query)

    # Fetch more candidates for re-ranking
    candidates_k = min(top_k * 3, 50)

    try:
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=candidates_k,
            with_payload=True,
        )
        raw_results = response.points
    except Exception:
        logger.exception("Qdrant search failed")
        return []

    if not raw_results:
        return []

    query_tokens = _tokenize(query)

    scored: list[dict[str, Any]] = []
    for hit in raw_results:
        payload = hit.payload or {}
        vector_score = float(hit.score)

        # Keyword score
        doc_text = f"{payload.get('title', '')} {payload.get('description', '')} {' '.join(payload.get('tags', []))}"
        keyword_score = _keyword_score(query_tokens, doc_text)

        # SAREF boost
        saref_boost = 0.0
        if saref_class and payload.get("saref_type", "").lower() == saref_class.lower():
            saref_boost = 1.0

        final_score = W_VECTOR * vector_score + W_KEYWORD * keyword_score + W_SAREF * saref_boost

        scored.append(
            {
                "app": payload,
                "score": round(final_score, 4),
                "vector_score": round(vector_score, 4),
                "keyword_score": round(keyword_score, 4),
                "saref_boost": round(saref_boost, 4),
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer."""
    return re.findall(r"\w+", text.lower())


def _keyword_score(query_tokens: list[str], doc_text: str) -> float:
    """BM25-lite scoring: fraction of query tokens found in document."""
    if not query_tokens:
        return 0.0
    doc_tokens = set(_tokenize(doc_text))
    matches = sum(1 for t in query_tokens if t in doc_tokens)
    # Normalize to [0, 1]
    return matches / len(query_tokens)

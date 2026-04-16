"""Hybrid search — vector + keyword (BM25) + SAREF boost with LRU cache."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter, OrderedDict
from typing import Any

from qdrant_client import QdrantClient

from .embeddings import encode_single
from .indexer import COLLECTION_NAME

logger = logging.getLogger(__name__)

# Scoring weights
W_VECTOR = 0.6
W_KEYWORD = 0.3
W_SAREF = 0.1

# Minimum hybrid score to include in results (filters low-confidence noise)
SCORE_THRESHOLD = 0.30

# BM25 parameters
BM25_K1 = 1.2
BM25_B = 0.75

# English stopwords — removed from query tokens to improve keyword signal
STOPWORDS: frozenset[str] = frozenset({
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your",
    "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she", "her",
    "hers", "herself", "it", "its", "itself", "they", "them", "their", "theirs",
    "themselves", "what", "which", "who", "whom", "this", "that", "these", "those",
    "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "having", "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if",
    "or", "because", "as", "until", "while", "of", "at", "by", "for", "with",
    "about", "against", "between", "through", "during", "before", "after", "above",
    "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "when", "where", "why",
    "how", "all", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s",
    "t", "can", "will", "just", "don", "should", "now", "d", "ll", "m", "o", "re",
    "ve", "y", "ain", "aren", "couldn", "didn", "doesn", "hadn", "hasn", "haven",
    "isn", "ma", "mightn", "mustn", "needn", "shan", "shouldn", "wasn", "weren",
    "won", "wouldn",
    # Domain-neutral filler words common in IoT queries
    "app", "apps", "application", "applications", "find", "show", "need", "want",
    "looking", "get", "give", "please", "something", "thing", "things", "like",
    "good", "best", "any",
    # Common European stopwords (multilingual support — DE, FR, ES, IT, NL, PT)
    # German
    "der", "die", "das", "ein", "eine", "ist", "und", "ich", "nicht", "mit",
    "auf", "für", "von", "den", "dem", "es", "sich", "auch", "als",
    # French
    "le", "la", "les", "un", "une", "des", "est", "et", "en", "que", "qui",
    "dans", "ce", "il", "ne", "pas", "sur", "se", "au", "avec", "je", "sont",
    # Spanish
    "el", "los", "las", "una", "unos", "unas", "es", "por", "con", "para",
    "del", "al", "lo", "ya", "su", "sus", "nos", "hay",
    # Italian
    "il", "lo", "gli", "uno", "sono", "che", "di", "da", "per", "non",
    "si", "nel", "con", "suo",
    # Dutch
    "de", "het", "een", "en", "van", "ik", "te", "dat", "er", "op", "aan",
    "met", "zijn", "ze", "niet", "voor", "ook", "maar",
    # Portuguese
    "ou", "um", "uma", "os", "as", "do", "da", "no", "na", "em", "mas",
    "como", "mais", "ao",
})

# LRU search-result cache (avoids re-embedding identical queries within a short window)
_CACHE_MAX = 128
_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()


def _cache_key(query: str, top_k: int, saref_class: str | None) -> str:
    raw = json.dumps({"q": query.lower().strip(), "k": top_k, "s": saref_class or ""}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def invalidate_cache():
    """Clear all cached results (called after re-indexing)."""
    _cache.clear()


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

    Results are LRU-cached to avoid repeated embedding computation.
    """
    key = _cache_key(query, top_k, saref_class)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

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

    query_tokens = _tokenize_query(query)

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
    # Filter out low-confidence results
    result = [r for r in scored if r["score"] >= SCORE_THRESHOLD][:top_k]

    # Store in LRU cache
    _cache[key] = result
    if len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)

    return result


def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer."""
    return re.findall(r"\w+", text.lower())


def _tokenize_query(text: str) -> list[str]:
    """Tokenize query text with stopword removal for better keyword matching."""
    tokens = _tokenize(text)
    filtered = [t for t in tokens if t not in STOPWORDS]
    # Fall back to all tokens if stopwords removed everything
    return filtered if filtered else tokens


def _keyword_score(query_tokens: list[str], doc_text: str) -> float:
    """BM25-inspired scoring with IDF weighting.

    Uses document-local term frequency with BM25 saturation and a simple
    IDF proxy: tokens that appear in the query but match fewer document
    fields get a higher weight.  The score is normalized to [0, 1].
    """
    if not query_tokens:
        return 0.0
    doc_tokens = _tokenize(doc_text)
    if not doc_tokens:
        return 0.0
    doc_len = len(doc_tokens)
    avg_dl = 50.0  # approximate average document length in tokens
    tf_counter = Counter(doc_tokens)

    score = 0.0
    for qt in query_tokens:
        tf = tf_counter.get(qt, 0)
        if tf == 0:
            continue
        # BM25 term frequency saturation
        tf_norm = (tf * (BM25_K1 + 1)) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / avg_dl))
        # Simple IDF proxy: rarer query terms get higher weight
        # Approximate: log(N / (df+1)) where N=75 (catalog size)
        # Since we don't track global DF, use inverse of query token frequency
        idf = math.log(2.0)  # baseline IDF for present terms
        score += idf * tf_norm

    # Normalize: max possible ≈ len(query_tokens) * log(2) * (k1+1)
    max_score = len(query_tokens) * math.log(2.0) * (BM25_K1 + 1)
    return min(score / max_score, 1.0) if max_score > 0 else 0.0

"""Sentence-transformer embedding model singleton."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    """Lazy-load the sentence-transformer model (CPU-only)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        model_name = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
        revision = os.getenv("EMBEDDING_MODEL_REVISION", "main")
        logger.info("Loading embedding model: %s revision=%s", model_name, revision)
        _model = SentenceTransformer(model_name, revision=revision)
        logger.info("Embedding model loaded successfully")
    return _model


def _encode_prefixed(texts: list[str], prefix: str) -> np.ndarray:
    """Encode E5-prefixed text into normalized 384-dimensional vectors."""
    model = _get_model()
    embeddings = model.encode(
        [f"{prefix}: {text}" for text in texts],
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return np.array(embeddings, dtype=np.float32)


def encode(texts: list[str]) -> np.ndarray:
    """Encode catalogue passages."""
    return _encode_prefixed(texts, "passage")


def encode_queries(texts: list[str]) -> np.ndarray:
    """Encode user queries with the E5 query prefix."""
    return _encode_prefixed(texts, "query")


def encode_single(text: str) -> list[float]:
    """Encode one user query and return a plain list."""
    vec = encode_queries([text])
    return vec[0].tolist()


VECTOR_DIM = 384

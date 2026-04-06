"""Sentence-transformer embedding model singleton."""

from __future__ import annotations

import logging
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

        model_name = "all-MiniLM-L6-v2"
        logger.info("Loading embedding model: %s", model_name)
        _model = SentenceTransformer(model_name)
        logger.info("Embedding model loaded successfully")
    return _model


def encode(texts: list[str]) -> np.ndarray:
    """Encode a list of texts into 384-dim embedding vectors."""
    model = _get_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return np.array(embeddings, dtype=np.float32)


def encode_single(text: str) -> list[float]:
    """Encode a single text and return as a plain list."""
    vec = encode([text])
    return vec[0].tolist()


VECTOR_DIM = 384

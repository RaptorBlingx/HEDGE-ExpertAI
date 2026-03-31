"""Qdrant indexer — upsert and manage app vectors."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from .embeddings import VECTOR_DIM, encode_single

logger = logging.getLogger(__name__)

COLLECTION_NAME = "hedge_apps"

_client: QdrantClient | None = None


def get_client(host: str = "qdrant", port: int = 6333) -> QdrantClient:
    """Get or create the Qdrant client singleton."""
    global _client
    if _client is None:
        _client = QdrantClient(host=host, port=port, check_compatibility=False)
        logger.info("Connected to Qdrant at %s:%d", host, port)
    return _client


def ensure_collection(client: QdrantClient) -> None:
    """Create the collection if it doesn't exist."""
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info("Created collection '%s'", COLLECTION_NAME)


def _app_to_index_text(app: dict[str, Any]) -> str:
    """Build the text to embed from app metadata."""
    tags = app.get("tags", [])
    if isinstance(tags, list):
        tag_str = " ".join(tags)
    else:
        tag_str = str(tags)
    return f"{app.get('title', '')} {app.get('description', '')} {tag_str}"


def index_app(client: QdrantClient, app: dict[str, Any]) -> None:
    """Index a single app into Qdrant."""
    text = _app_to_index_text(app)
    vector = encode_single(text)
    point = PointStruct(
        id=_app_id_to_int(app["id"]),
        vector=vector,
        payload=app,
    )
    client.upsert(collection_name=COLLECTION_NAME, points=[point])


def index_batch(client: QdrantClient, apps: list[dict[str, Any]]) -> int:
    """Index a batch of apps. Returns count of indexed apps."""
    if not apps:
        return 0
    texts = [_app_to_index_text(a) for a in apps]
    from .embeddings import encode

    vectors = encode(texts)
    points = [
        PointStruct(
            id=_app_id_to_int(app["id"]),
            vector=vec.tolist(),
            payload=app,
        )
        for app, vec in zip(apps, vectors)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info("Indexed %d apps", len(points))
    return len(points)


def delete_app(client: QdrantClient, app_id: str) -> None:
    """Delete an app from the index."""
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=[_app_id_to_int(app_id)],
    )


def get_app_by_id(client: QdrantClient, app_id: str) -> dict[str, Any] | None:
    """Retrieve an app's payload from Qdrant by ID."""
    try:
        points = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[_app_id_to_int(app_id)],
            with_payload=True,
        )
        if points:
            return points[0].payload
    except Exception:
        logger.exception("Failed to retrieve app %s", app_id)
    return None


def _app_id_to_int(app_id: str) -> int:
    """Convert app ID string (e.g. 'app-001') to a stable integer hash.

    Uses SHA-256 for deterministic hashing across processes.
    """
    h = hashlib.sha256(app_id.encode()).hexdigest()
    return int(h[:15], 16)

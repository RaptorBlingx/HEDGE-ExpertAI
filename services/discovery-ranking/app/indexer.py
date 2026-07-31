"""Qdrant indexer — upsert and manage app vectors."""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from hedge_shared.models_v2 import AppMetadataV2
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    CreateAlias,
    CreateAliasOperation,
    DeleteAlias,
    DeleteAliasOperation,
    Distance,
    PointStruct,
    VectorParams,
)

from .embeddings import VECTOR_DIM, encode

logger = logging.getLogger(__name__)

COLLECTION_VERSION = os.getenv("QDRANT_COLLECTION_VERSION", "v2")
COLLECTION_NAME = f"hedge_apps_{COLLECTION_VERSION}"
COLLECTION_ALIAS = "hedge_apps_current"

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
    try:
        aliases = {item.alias_name for item in client.get_aliases().aliases}
        if COLLECTION_ALIAS not in aliases:
            client.update_collection_aliases(
                change_aliases_operations=[
                    CreateAliasOperation(
                        create_alias=CreateAlias(
                            collection_name=COLLECTION_NAME,
                            alias_name=COLLECTION_ALIAS,
                        )
                    )
                ]
            )
    except Exception:
        # The physical versioned collection remains usable if an older client
        # does not expose aliases; readiness and promotion tooling surface this.
        logger.exception("Unable to create Qdrant collection alias")


def _app_to_index_text(app: dict[str, Any]) -> str:
    """Build the text to embed from app metadata."""
    if app.get("schema_version") == "2.0":
        return AppMetadataV2.model_validate(app).to_index_text("en")
    tags = app.get("tags", [])
    if isinstance(tags, list):
        tag_str = " ".join(tags)
    else:
        tag_str = str(tags)
    return f"{app.get('title', '')} {app.get('description', '')} {tag_str}"


def index_app(client: QdrantClient, app: dict[str, Any]) -> None:
    """Index a single app into Qdrant."""
    text = _app_to_index_text(app)
    vector = encode([text])[0].tolist()
    point = PointStruct(
        id=_app_id_to_int(app["id"]),
        vector=vector,
        payload=app,
    )
    client.upsert(collection_name=COLLECTION_ALIAS, points=[point])


def index_batch(
    client: QdrantClient,
    apps: list[dict[str, Any]],
    *,
    revisions: dict[str, int] | None = None,
    collection_name: str = COLLECTION_ALIAS,
) -> int:
    """Index a batch of apps. Returns count of indexed apps."""
    if not apps:
        return 0
    texts = [_app_to_index_text(a) for a in apps]
    vectors = encode(texts)
    points = [
        PointStruct(
            id=_app_id_to_int(app["id"]),
            vector=vec.tolist(),
            payload={
                **app,
                "_index_revision": (revisions or {}).get(str(app["id"]), 1),
                "_index_model": os.getenv(
                    "EMBEDDING_MODEL",
                    "intfloat/multilingual-e5-small",
                ),
                "_index_model_revision": os.getenv("EMBEDDING_MODEL_REVISION", "main"),
            },
        )
        for app, vec in zip(apps, vectors, strict=True)
    ]
    client.upsert(collection_name=collection_name, points=points)
    logger.info("Indexed %d apps", len(points))
    return len(points)


def delete_app(client: QdrantClient, app_id: str) -> None:
    """Delete an app from the index."""
    client.delete(
        collection_name=COLLECTION_ALIAS,
        points_selector=[_app_id_to_int(app_id)],
    )


def apply_operations(client: QdrantClient, operations: list[dict[str, Any]]) -> int:
    """Apply idempotent revisioned upserts/deletes."""
    upserts: list[dict[str, Any]] = []
    revisions: dict[str, int] = {}
    applied = 0
    for operation in operations:
        app_id = str(operation["app_id"])
        revision = int(operation["revision"])
        if operation["operation"] == "delete":
            delete_app(client, app_id)
            applied += 1
            continue
        app = AppMetadataV2.model_validate(operation["app"])
        if app.id != app_id:
            raise ValueError("operation app_id does not match payload")
        upserts.append(app.model_dump(mode="json", exclude={"checksum"}))
        revisions[app.id] = revision
    if upserts:
        applied += index_batch(client, upserts, revisions=revisions)
    return applied


def get_app_by_id(client: QdrantClient, app_id: str) -> dict[str, Any] | None:
    """Retrieve an app's payload from Qdrant by ID."""
    try:
        points = client.retrieve(
            collection_name=COLLECTION_ALIAS,
            ids=[_app_id_to_int(app_id)],
            with_payload=True,
        )
        if points:
            return points[0].payload
    except Exception:
        logger.exception("Failed to retrieve app %s", app_id)
    return None


def rebuild_collection(client: QdrantClient, collection_name: str) -> dict[str, Any]:
    """Build a complete derived index and atomically promote its alias."""
    import re

    from hedge_shared.storage import list_catalogue_apps

    if not re.fullmatch(r"hedge_apps_v2_[a-z0-9_-]{3,40}", collection_name):
        raise ValueError("invalid versioned collection name")
    existing = {item.name for item in client.get_collections().collections}
    if collection_name in existing:
        raise ValueError("target collection already exists")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    total, _ = list_catalogue_apps(limit=1)
    indexed = 0
    for offset in range(0, total, 50):
        _, apps = list_catalogue_apps(limit=50, offset=offset)
        indexed += index_batch(client, apps, collection_name=collection_name)
    if indexed != total:
        raise RuntimeError(f"reindex count mismatch: expected {total}, indexed {indexed}")
    promote_collection(client, collection_name, expected_count=total)
    return {"collection": collection_name, "indexed": indexed, "promoted": True}


def promote_collection(
    client: QdrantClient,
    collection_name: str,
    *,
    expected_count: int | None = None,
) -> dict[str, Any]:
    """Validate and atomically promote an existing collection for rollback."""
    import re

    from hedge_shared.storage import list_catalogue_apps

    if not re.fullmatch(r"hedge_apps_v2_[a-z0-9_-]{3,40}", collection_name):
        raise ValueError("invalid versioned collection name")
    existing = {item.name for item in client.get_collections().collections}
    if collection_name not in existing:
        raise ValueError("target collection does not exist")
    authoritative_count = expected_count
    if authoritative_count is None:
        authoritative_count, _ = list_catalogue_apps(limit=1)
    indexed_count = int(client.count(collection_name=collection_name, exact=True).count)
    if indexed_count != authoritative_count:
        raise ValueError(
            f"collection count mismatch: expected {authoritative_count}, indexed {indexed_count}"
        )
    aliases = {item.alias_name for item in client.get_aliases().aliases}
    operations = []
    if COLLECTION_ALIAS in aliases:
        operations.append(DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=COLLECTION_ALIAS)))
    operations.append(
        CreateAliasOperation(
            create_alias=CreateAlias(
                collection_name=collection_name,
                alias_name=COLLECTION_ALIAS,
            )
        )
    )
    client.update_collection_aliases(change_aliases_operations=operations)
    return {
        "collection": collection_name,
        "indexed": indexed_count,
        "promoted": True,
    }


def _app_id_to_int(app_id: str) -> int:
    """Convert app ID string (e.g. 'app-001') to a stable integer hash.

    Uses SHA-256 for deterministic hashing across processes.
    """
    h = hashlib.sha256(app_id.encode()).hexdigest()
    return int(h[:15], 16)

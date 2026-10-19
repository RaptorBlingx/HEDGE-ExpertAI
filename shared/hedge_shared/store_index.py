"""Reconcile a scoped derived Store index from durable authoritative membership."""
import os
from types import ModuleType

from qdrant_client import QdrantClient, models

from . import store_sync
from .store_knowledge import PREPARATION_VERSION
from .store_v1 import StoreAppMetadata


def repair_store_index(
    store_id: str, vector: QdrantClient, indexer: ModuleType, collection: str
) -> None:
    # Reconcile durable desired state with actual derived points, including
    # recovery after a crash, failed write or complete Qdrant data loss.
    if not vector.collection_exists(collection):
        vector.create_collection(
            collection,
            vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE),
        )
    rows = store_sync.members(store_id)
    for start in range(0, len(rows), 128):
        batch = rows[start : start + 128]
        points = {
            p.id: p
            for p in vector.retrieve(
                collection, [indexer._app_id_to_int(r["id"]) for r in batch], with_payload=True
            )
        }
        for row in batch:
            app = StoreAppMetadata.model_validate(row["payload"])
            point = points.get(indexer._app_id_to_int(row["id"]))
            desired = row["available"] and bool(app.to_index_text())
            if desired:
                if (
                    not point
                    or point.payload.get("_index_revision") != row["revision"]
                    or point.payload.get("store_id") != store_id
                    or point.payload.get("app_id") != app.app_id
                    or point.payload.get("_index_preparation_version") != PREPARATION_VERSION
                    or point.payload.get("_index_model") != os.getenv(
                        "EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
                    or point.payload.get("_index_model_revision") != os.getenv(
                        "EMBEDDING_MODEL_REVISION", "main")
                ):
                    applied = indexer.apply_operations(
                        vector,
                        [
                            {
                                "app_id": row["id"],
                                "revision": row["revision"],
                                "operation": "upsert",
                                "app": row["payload"],
                            }
                        ],
                        store_id=store_id,
                        collection_name=collection,
                    )
                    if applied != 1:
                        raise RuntimeError("Scoped index revision was not applied")
            elif point:
                indexer.delete_app(vector, row["id"], collection_name=collection)
            store_sync.indexed(store_id, row["id"], row["revision"], row["available"])


"""Private durable Store workspace using the existing service implementations.

No public routes/indexing, browser credential extraction or source mutations.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import uuid
from contextlib import ExitStack, asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from hedge_shared import models_v2, storage, store_sync
from hedge_shared.config import Settings
from hedge_shared.store_knowledge import PREPARATION_VERSION, project
from hedge_shared.store_v1 import StoreAppMetadata
from qdrant_client import QdrantClient, models

from scripts.store_v1_browser import create_app
from scripts.store_v1_playground import ROOT, Playground, load_service


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
                    or point.payload.get("_index_model") != os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
                    or point.payload.get("_index_model_revision") != os.getenv("EMBEDDING_MODEL_REVISION", "main")
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


@contextmanager
def workspace():
    # Separate durable DB; never relax the original disposable runner's guard.
    url = urlparse(os.environ["DATABASE_URL"])
    if (url.hostname, url.path) != ("database", "/hedge_store_workspace"):
        raise ValueError("Use the private Store workspace launcher")
    spec = importlib.util.spec_from_file_location("workspace_migrate", ROOT / "database/migrate.py")
    migrate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migrate)
    migrate.main()
    store_id = os.environ["HEDGE_STORE_ID"]
    ingest = load_service("workspace_ingest", "metadata-ingest")
    discovery = load_service("workspace_discovery", "discovery-ranking")
    recommend = load_service("workspace_expert", "expert-recommend")("recommender")
    answers = __import__(recommend.__package__ + ".store_conversation", fromlist=["respond"])
    chat = load_service("workspace_chat", "chat-intent")("routes")
    policy_module = __import__(chat.__package__ + ".store_conversation", fromlist=["StoreConversation"])
    client = ingest("client").HedgeApiClient(
        "https://store.haslab-dataspace.pt/backend/api/v1",
        store_id=store_id,
        token_file="/credentials/token",
        timeout=20,
        max_retries=1,
    )
    collection = (
        "hedge_store_offline_" + uuid.uuid5(uuid.NAMESPACE_URL, "private-store:" + store_id).hex
    )
    vector = QdrantClient(url="http://vectors:6333", check_compatibility=False, timeout=5)
    indexer = discovery("indexer")

    state = store_sync.status(store_id)
    if state.get("snapshot_at") is None and Path("/bootstrap/bootstrap-apps.json").is_file():
        # Explicitly authorized saved getAllApps response, never labelled fresh.
        with Path("/bootstrap/bootstrap-apps.json").open("rb") as saved:
            body = saved.read(client.MAX_RESPONSE_BYTES + 1)
        if len(body) > client.MAX_RESPONSE_BYTES:
            raise ValueError("Saved Store response exceeds the transport size bound")
        raw = json.loads(
            body,
            object_pairs_hook=ingest("client")._unique_json_object,
            parse_constant=ingest("client")._reject_json_constant,
        )
        if not isinstance(raw, list):
            raise ValueError("Saved catalogue must be a getAllApps array")
        provenance = json.loads(Path("/bootstrap/bootstrap-provenance.json").read_text())
        captured_at = datetime.fromtimestamp(provenance["captured_file_mtime"], UTC)
        ingest("snapshot").reconcile_catalogue_snapshot(
            "private-store-workspace",
            lambda: raw,
            store_id=store_id,
            managed_source="authorized_snapshot",
            captured_at=captured_at,
        )
    repair_store_index(store_id, vector, indexer, collection)
    # An unchanged vector index does not load the query encoder. Warm it before
    # serving, as Discovery's existing lifespan does, rather than on a user's turn.
    if os.getenv("STORE_PLAYGROUND_E5") == "true":
        try:
            discovery("embeddings").encode_single("catalogue readiness")
        except Exception:
            logging.getLogger(__name__).warning("Query encoder warmup unavailable; lexical retrieval remains usable")

    def refresh() -> dict[str, Any]:
        try:
            if not Path("/credentials/token").is_file():
                raise ingest("client").StoreApiError(
                    "Store authorization not provisioned", status_code=401
                )
            receipt = ingest("snapshot").reconcile_catalogue_snapshot(
                "private-store-workspace",
                client.fetch_catalogue_records,
                store_id=store_id,
                managed_source="authorized_api",
            )
        except ingest("client").StoreApiError as error:
            store_sync.failed(store_id, error.status_code)
            receipt = {
                "source_error": "authorization_required"
                if error.status_code in (401, 403)
                else "source_unavailable"
            }
        repair_store_index(store_id, vector, indexer, collection)
        return {"ingestion": receipt, "synchronization": store_sync.status(store_id)}

    def resolve(identities: list[str] | None) -> list[dict[str, Any]]:
        if store_sync.status(store_id).get("snapshot_at") is None:
            raise HTTPException(status_code=503, detail="No authorized Store observation available")
        if identities is None:
            identities = [row["id"] for row in store_sync.members(store_id) if row["available"]]
        rows = storage.get_catalogue_apps(identities, store_id=store_id)
        return [
            project(rows[i])
            for i in identities
            if i in rows
        ]

    async def search(**kwargs):
        return playground.recommend(**kwargs)

    def scoped_search(query, *, locale, filters, limit):
        return discovery("searcher_v2").search_apps_v2(
            vector,
            query=query,
            locale=locale,
            filters=models_v2.SearchFilters.model_validate(filters),
            limit=limit,
            store_id=store_id,
            collection_name=collection,
        )

    def no_model(*args, **kwargs):
        raise RuntimeError("Deterministic Store source quotations")

    with ExitStack() as stack:
        stack.callback(vector.close)
        stack.enter_context(patch.object(recommend, "_search_apps_v2", scoped_search))
        # Keep retrieval orchestration deterministic. Dialogue owns bounded model
        # interpretation and reviewed synthesis after authoritative App selection.
        stack.enter_context(patch.object(recommend, "OllamaClient", no_model))
        policy = policy_module.StoreConversation(
            search, resolve, recommend._recommendation_narrative,
            answers.plan, answers.respond, lambda: store_sync.status(store_id),
            decide=recommend._recommendation_decision,
            present=answers.prepared_answer,
        )
        playground = Playground(chat, recommend, models_v2, [], policy)
        playground.source = "managed-authorized-store"
        playground.refresh = refresh
        playground.sync_status = lambda: store_sync.status(store_id)
        playground.catalogue = resolve
        yield playground


@asynccontextmanager
async def lifespan(app):
    with workspace() as playground:
        ui = create_app(playground)
        await asyncio.to_thread(playground.refresh)
        app.mount("/", ui)

        async def polling():
            while True:
                await asyncio.sleep(Settings().STORE_SYNC_INTERVAL_SECONDS)
                async with ui.state.refresh_lock:
                    try:
                        await asyncio.to_thread(playground.refresh)
                    except Exception:
                        # A failed index remains pending and is retried next time.
                        # No payloads or exception text enter operational logs.
                        store_sync.failed(os.environ["HEDGE_STORE_ID"], None)

        task = asyncio.create_task(polling())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

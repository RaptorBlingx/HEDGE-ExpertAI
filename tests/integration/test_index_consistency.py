"""Crash/replay and PostgreSQL-authoritative retrieval using disposable stores.

HEDGE_TEST_DATABASE_URL must target hedge_phase1_test. HEDGE_TEST_QDRANT_URL
must explicitly target the isolated vectors container; embeddings are deterministic.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlparse

import httpx
import pytest
from hedge_shared import storage
from hedge_shared.models_v2 import AppMetadataV2, SearchFilters
from hedge_shared.store_v1 import StoreAppMetadata
from qdrant_client import QdrantClient, models

from .test_catalogue_snapshot import wait_for_blocked_lock
from .test_store_v1_persistence import database as database
from .test_store_v1_persistence import migrate, rows

ROOT = Path(__file__).parents[2]
package = ModuleType("consistency_discovery")
package.__path__ = [str(ROOT / "services/discovery-ranking/app")]
sys.modules[package.__name__] = package
embeddings = ModuleType("consistency_discovery.embeddings")
embeddings.VECTOR_DIM = 384
VECTOR = [1.0] + [0.0] * 383
embeddings.encode = lambda texts: [SimpleNamespace(tolist=lambda: VECTOR) for _ in texts]
embeddings.encode_single = lambda query: VECTOR
sys.modules[embeddings.__name__] = embeddings
indexer = importlib.import_module("consistency_discovery.indexer")
searcher = importlib.import_module("consistency_discovery.searcher_v2")
spec = importlib.util.spec_from_file_location(
    "consistency_ingest",
    ROOT / "services/metadata-ingest/app/__init__.py",
    submodule_search_locations=[str(ROOT / "services/metadata-ingest/app")],
)
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
ingest = importlib.import_module("consistency_ingest.tasks.ingest")


@pytest.fixture
def catalogue(database):
    migrate.main()
    app = database.model_copy(update={"id": "index-test"})
    save(app)
    return app


def save(app):
    return storage.upsert_catalogue_app(storage.create_ingestion_run("index-tests"), app)


def operation(app, revision=1, kind="upsert"):
    return {
        "app_id": app.id,
        "revision": revision,
        "operation": kind,
        "app": app.model_dump(mode="json", exclude={"checksum"}) if kind == "upsert" else None,
    }


def item():
    return next(r for r in rows("indexing_outbox") if r["app_id"] == "index-test")


def expire(claim):
    with storage.connection() as conn:
        conn.execute(
            "UPDATE indexing_outbox SET updated_at = now() - interval '4 minutes' WHERE id = %s",
            (claim["id"],),
        )


def test_abandoned_lease_is_reclaimed_and_late_acknowledgements_are_fenced(catalogue):
    first = storage.pending_outbox(limit=1)[0]
    assert storage.pending_outbox(limit=1) == []
    expire(first)
    second = storage.pending_outbox(limit=1)[0]
    assert second["id"] == first["id"] and second["attempts"] == 2
    assert not storage.complete_outbox_item(
        first["id"], app_id=first["app_id"], revision=1, claimed_at=first["updated_at"]
    )
    assert not storage.fail_outbox_item(first["id"], "late failure", claimed_at=first["updated_at"])
    assert storage.complete_outbox_item(
        second["id"], app_id=second["app_id"], revision=1, claimed_at=second["updated_at"]
    )
    assert item()["status"] == "completed"


@pytest.mark.parametrize("interrupted", [False, True])
def test_exhausted_work_is_retained_visible_and_explicitly_replayable(catalogue, interrupted):
    with storage.connection() as conn:
        conn.execute("UPDATE indexing_outbox SET attempts = 9 WHERE id = %s", (item()["id"],))
    last = storage.pending_outbox(limit=1)[0]
    if interrupted:
        expire(last)
    else:
        assert storage.fail_outbox_item(
            last["id"], "Qdrant unavailable", claimed_at=last["updated_at"]
        )
    assert storage.pending_outbox(limit=1) == []
    failed = item()
    assert failed["status"] == "failed" and failed["attempts"] == 10 and failed["last_error"]
    assert storage.outbox_status() == {"outstanding": 1, "exhausted": 1}
    assert storage.retry_outbox_item(last["id"])
    fresh = storage.pending_outbox(limit=1)[0]
    assert fresh["payload"] == last["payload"] and fresh["attempts"] == 1
    assert not storage.fail_outbox_item(last["id"], "old worker", claimed_at=last["updated_at"])
    assert not storage.retry_outbox_item(last["id"])


def test_workers_cannot_claim_the_same_unexpired_operation(catalogue):
    barrier = Barrier(2)

    def claim():
        barrier.wait(timeout=5)
        return storage.pending_outbox(limit=1)

    with ThreadPoolExecutor(2) as pool:
        a, b = [f.result(timeout=5) for f in [pool.submit(claim), pool.submit(claim)]]
    assert len(a) + len(b) == 1
    assert item()["attempts"] == 1


def test_old_completion_does_not_mark_new_revision_searchable(catalogue):
    claim = storage.pending_outbox(limit=1)[0]
    changed = catalogue.model_copy(update={"tags": [*catalogue.tags, "changed"]})
    save(changed)
    assert storage.complete_outbox_item(
        claim["id"], app_id=catalogue.id, revision=1, claimed_at=claim["updated_at"]
    )
    row = storage.get_catalogue_apps([catalogue.id])[catalogue.id]
    assert row["revision"] == 2
    assert next(r for r in rows("catalog_apps") if r["id"] == catalogue.id)["searchable_at"] is None


@pytest.fixture
def vectors(monkeypatch):
    url = os.getenv("HEDGE_TEST_QDRANT_URL")
    if not url:
        pytest.skip("requires explicitly isolated HEDGE_TEST_QDRANT_URL")
    assert urlparse(url).hostname == "vectors"
    client = QdrantClient(url=url, check_compatibility=False, timeout=3)
    name = "test_" + uuid.uuid4().hex
    client.create_collection(
        name, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE)
    )
    monkeypatch.setattr(indexer, "COLLECTION_ALIAS", name)
    monkeypatch.setattr(searcher, "COLLECTION_ALIAS", name)
    cache = MagicMock()
    cache.get.return_value = None
    monkeypatch.setattr(searcher, "_cache", lambda: cache)
    yield client, cache
    client.delete_collection(name)
    client.close()


def vector_payload(client, app):
    points = client.retrieve(
        indexer.COLLECTION_ALIAS, [indexer._app_id_to_int(app.id)], with_payload=True
    )
    return points[0].payload if points else None


def withdraw(app):
    run = storage.create_ingestion_run("index-tests")
    with storage.catalogue_snapshot("index-tests") as conn:
        storage.tombstone_missing_apps(run, conn=conn)


def search(client):
    return searcher.search_apps_v2(
        client,
        query="energy",
        locale="en",
        filters=SearchFilters(),
        limit=5,
        catalogue_revision="deliberately-stale-cache-namespace",
    )


def test_reversed_operations_and_withdrawal_reappearance_cannot_regress_vectors(catalogue, vectors):
    client, _ = vectors
    changed = catalogue.model_copy(update={"tags": [*catalogue.tags, "changed"]})
    save(changed)
    assert indexer.apply_operations(client, [operation(changed, 2), operation(catalogue)]) == 1
    assert vector_payload(client, catalogue)["_index_revision"] == 2
    withdraw(changed)
    assert (
        indexer.apply_operations(client, [operation(changed, 3, "delete"), operation(changed, 2)])
        == 1
    )
    assert vector_payload(client, catalogue) is None
    save(changed)
    assert (
        indexer.apply_operations(client, [operation(changed, 4), operation(changed, 3, "delete")])
        == 1
    )
    assert vector_payload(client, catalogue)["_index_revision"] == 4


def test_concurrent_catalogue_update_waits_for_vector_write(catalogue, vectors):
    client, _ = vectors
    started, release = Event(), Event()
    real = client.upsert

    def blocked(**kwargs):
        started.set()
        assert release.wait(5)
        return real(**kwargs)

    client.upsert = blocked
    changed = catalogue.model_copy(update={"tags": [*catalogue.tags, "changed"]})
    with ThreadPoolExecutor(2) as pool:
        old = pool.submit(indexer.apply_operations, client, [operation(catalogue)])
        assert started.wait(5)
        update = pool.submit(save, changed)
        try:
            wait_for_blocked_lock("transactionid")
            assert not update.done()
        finally:
            release.set()
        assert old.result(timeout=5) == 1
        assert update.result(timeout=5) == "updated"
    client.upsert = real
    assert indexer.apply_operations(client, [operation(changed, 2), operation(catalogue)]) == 1
    assert vector_payload(client, catalogue)["_index_revision"] == 2


def test_payload_tampering_and_source_only_store_rows_never_enter_index(catalogue, vectors):
    client, _ = vectors
    changed = catalogue.model_copy(update={"tags": ["tampered"]})
    with pytest.raises(ValueError, match="authoritative revision"):
        indexer.apply_operations(client, [operation(changed)])
    store = StoreAppMetadata(store_id="Store", app_id="App", active=True, visible=True)
    storage.upsert_catalogue_app(storage.create_ingestion_run("offline-store"), store)
    assert (
        indexer.apply_operations(
            client, [{"app_id": store.id, "revision": 1, "operation": "delete"}]
        )
        == 0
    )
    with pytest.raises(ValueError):
        indexer.apply_operations(
            client,
            [
                {
                    "app_id": store.id,
                    "revision": 1,
                    "operation": "upsert",
                    "app": store.model_dump(mode="json"),
                }
            ],
        )
    assert client.count(indexer.COLLECTION_ALIAS).count == 0


@pytest.mark.parametrize("hard_crash", [False, True])
def test_crash_after_qdrant_write_replays_without_losing_durable_work(
    catalogue, vectors, monkeypatch, hard_crash
):
    client, _ = vectors
    calls = []

    class WorkerInterrupted(BaseException):
        pass

    def post(url, *, json, timeout):
        applied = indexer.apply_operations(client, json["operations"])
        calls.append(applied)
        if len(calls) == 1:
            if hard_crash:
                raise WorkerInterrupted("worker stopped after vector write")
            raise httpx.ReadTimeout("acknowledgement lost after write")
        return httpx.Response(200, json={"applied": applied}, request=httpx.Request("POST", url))

    monkeypatch.setattr(ingest.httpx, "post", post)
    if hard_crash:
        with pytest.raises(WorkerInterrupted):
            ingest.deliver_pending_outbox(limit=1)
        assert item()["status"] == "processing"
        expire(item())
    else:
        assert ingest.deliver_pending_outbox(limit=1)["failed"] == 1
        assert item()["status"] == "failed"
    assert vector_payload(client, catalogue)["_index_revision"] == 1
    with storage.connection() as conn:
        conn.execute(
            "UPDATE indexing_outbox SET next_attempt_at = now() WHERE id = %s", (item()["id"],)
        )
    result = ingest.deliver_pending_outbox(limit=1)
    assert result == {"delivered": 1, "failed": 0, "outstanding": 0, "exhausted": 0}
    assert item()["attempts"] == 2 and item()["status"] == "completed"
    assert client.count(indexer.COLLECTION_ALIAS).count == 1


def test_stale_vectors_and_cached_rankings_cannot_return_withdrawn_metadata(catalogue, vectors):
    client, cache = vectors
    indexer.apply_operations(client, [operation(catalogue)])
    assert catalogue.id in [r["app"]["id"] for r in search(client)]
    cache.get.return_value = cache.setex.call_args.args[2]
    withdraw(catalogue)  # Deliberately leave the vector and cache untouched.
    assert catalogue.id not in [r["app"]["id"] for r in search(client)]
    assert vector_payload(client, catalogue) is not None


def test_updated_metadata_is_lexically_available_before_vector_delivery(catalogue, vectors):
    client, cache = vectors
    indexer.apply_operations(client, [operation(catalogue)])
    search(client)
    cache.get.return_value = cache.setex.call_args.args[2]
    title = {**catalogue.title.model_dump(mode="json"), "en": "New Energy Monitor"}
    changed = AppMetadataV2.model_validate(
        {
            **catalogue.model_dump(mode="json", exclude={"checksum"}),
            "title": title,
            "tags": [*catalogue.tags, "new"],
        }
    )
    save(changed)
    found = next(r for r in search(client) if r["app"]["id"] == catalogue.id)
    assert found["app"]["title"] == title and found["evidence_fields"] == ["lexical"]
    assert vector_payload(client, catalogue)["_index_revision"] == 1


def test_vector_failure_does_not_hide_unindexed_lexical_apps(catalogue, vectors, monkeypatch):
    client, cache = vectors

    def unavailable(**kwargs):
        raise TimeoutError("vector index down")

    monkeypatch.setattr(client, "query_points", unavailable)
    found = next(r for r in search(client) if r["app"]["id"] == catalogue.id)
    assert found["evidence_fields"] == ["lexical"]
    cache.setex.assert_not_called()
    assert next(r for r in rows("catalog_apps") if r["id"] == catalogue.id)["searchable_at"] is None

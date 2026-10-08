"""Index write fencing, acknowledgement checks, and degraded readiness without I/O."""

from __future__ import annotations

import importlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Response
from hedge_shared.models_v2 import AppMetadataV2

ROOT = Path(__file__).parents[2]
package = ModuleType("unit_index_discovery")
package.__path__ = [str(ROOT / "services/discovery-ranking/app")]
sys.modules[package.__name__] = package
embeddings = ModuleType("unit_index_discovery.embeddings")
embeddings.VECTOR_DIM = 384
embeddings.encode = MagicMock(return_value=[SimpleNamespace(tolist=lambda: [0.1] * 384)])
embeddings.encode_single = MagicMock(return_value=[0.1] * 384)
sys.modules[embeddings.__name__] = embeddings
indexer = importlib.import_module("unit_index_discovery.indexer")
routes = importlib.import_module("unit_index_discovery.routes")
main = importlib.import_module("unit_index_discovery.main")


@pytest.fixture
def current(monkeypatch):
    payload = json.loads((ROOT / "services/mock-api/app/data/apps-v2.json").read_text())[0]
    app = AppMetadataV2.model_validate(payload)
    row = {
        "id": app.id,
        "revision": 7,
        "payload": payload,
        "checksum": app.checksum,
        "schema_version": "2.0",
        "active": True,
    }

    @contextmanager
    def locked(app_id):
        yield row

    monkeypatch.setattr(indexer, "catalogue_index_app", locked)
    monkeypatch.setattr(
        indexer, "get_catalogue_apps", lambda ids: {app.id: row} if row["active"] else {}
    )
    return app, row


def op(app, revision=7, kind="upsert"):
    return {
        "app_id": app.id,
        "revision": revision,
        "operation": kind,
        "app": app.model_dump(mode="json", exclude={"checksum"}),
    }


@pytest.mark.parametrize("revision", [6, 8])
def test_obsolete_or_future_operations_never_write(current, revision):
    app, _ = current
    client = MagicMock()
    assert indexer.apply_operations(client, [op(app, revision)]) == 0
    client.upsert.assert_not_called()


@pytest.mark.parametrize("active,kind", [(False, "upsert"), (True, "delete")])
def test_operation_must_match_publication_state(current, active, kind):
    app, row = current
    row["active"] = active
    client = MagicMock()
    assert indexer.apply_operations(client, [op(app, kind=kind)]) == 0
    client.upsert.assert_not_called()
    client.delete.assert_not_called()


@pytest.mark.parametrize("kind", ["upsert", "delete"])
def test_index_waits_for_completed_ordered_writes(current, kind):
    app, row = current
    row["active"] = kind == "upsert"
    client = MagicMock()
    write = client.upsert if kind == "upsert" else client.delete
    write.return_value = SimpleNamespace(status="completed")
    assert indexer.apply_operations(client, [op(app, kind=kind)]) == 1
    assert write.call_args.kwargs["wait"] is True
    assert write.call_args.kwargs["ordering"] == "strong"
    write.return_value = SimpleNamespace(status="acknowledged")
    with pytest.raises(RuntimeError, match="did not complete"):
        indexer.apply_operations(client, [op(app, kind=kind)])


def test_unversioned_live_batch_and_source_profiles_are_rejected(current):
    app, _ = current
    client = MagicMock()
    with pytest.raises(ValueError, match="revisioned"):
        indexer.index_batch(client, [op(app)["app"]], revisions={app.id: 7})
    with pytest.raises(HTTPException) as error:
        routes.index_apps(
            routes.IndexRequest(apps=[{"source_profile": "hedge-store-v1", "app_id": "A"}])
        )
    assert error.value.status_code == 422
    client.upsert.assert_not_called()


def test_legacy_search_and_details_use_current_authority(current, monkeypatch):
    app, row = current
    monkeypatch.setattr(routes, "get_client", MagicMock)
    monkeypatch.setattr(
        routes,
        "hybrid_search",
        lambda *a, **k: [
            {"app": {**row["payload"], "_index_revision": 7, "title": {"en": "stale"}}}
        ],
    )
    monkeypatch.setattr(routes, "get_catalogue_apps", lambda ids: {app.id: row})
    monkeypatch.setattr(routes, "get_catalogue_app", lambda key: row["payload"])
    assert (
        routes.search_apps(routes.SearchRequest(query="energy"))["results"][0]["app"]
        == row["payload"]
    )
    assert routes.get_app(app.id) == row["payload"]
    monkeypatch.setattr(routes, "get_catalogue_app", lambda key: None)
    with pytest.raises(HTTPException) as error:
        routes.get_app(app.id)
    assert error.value.status_code == 404


def test_readiness_keeps_lexical_service_available_when_vector_store_fails(monkeypatch):
    client = MagicMock()
    client.get_collections.side_effect = TimeoutError("vector store unavailable")
    monkeypatch.setattr(main, "get_client", lambda: client)
    monkeypatch.setattr(main, "ping_database", lambda: True)
    response = Response()
    result = main.ready(response)
    assert response.status_code == 200
    assert result["status"] == "ok" and result["postgres"] and not result["qdrant"]
    monkeypatch.setattr(main, "ping_database", lambda: False)
    response = Response()
    main.ready(response)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_lifespan_starts_lexical_service_when_vector_initialization_fails(monkeypatch):
    monkeypatch.setattr(main, "get_client", MagicMock)

    def unavailable(client):
        raise TimeoutError("vector store unavailable")

    monkeypatch.setattr(main, "ensure_collection", unavailable)
    async with main.lifespan(main.app):
        assert main.live()["status"] == "ok"

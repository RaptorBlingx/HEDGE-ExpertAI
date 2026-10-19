"""Managed Store observations through real client, PostgreSQL, Qdrant and browser API."""

from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from hedge_shared import storage, store_sync
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_browser import create_app
from scripts.store_v1_workspace import repair_store_index

from .test_store_v1_persistence import database as database
from .test_store_v1_recommendations import STORE, client_module, indexer, snapshot
from .test_store_v1_recommendations import offline as offline


def observe(records):
    client = client_module.HedgeApiClient(
        "https://store.example/api/v1",
        store_id=STORE,
        token="authorized-test-token",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=records)),
    )
    return snapshot.reconcile_catalogue_snapshot(
        "managed-test",
        client.fetch_catalogue_records,
        store_id=STORE,
        managed_source="authorized_api",
    )


def row(identity, **fields):
    return {
        "appId": identity,
        "active": True,
        "visible": True,
        "name": identity,
        "description": "thermal diagnostics",
        **fields,
    }


def identity(native):
    return StoreAppMetadata(store_id=STORE, app_id=native).id


def available():
    return storage.get_catalogue_apps([r["id"] for r in store_sync.members(STORE)], store_id=STORE)


def test_real_client_applies_withdrawal_despite_malformed_neighbor_and_self(offline):
    observe([row("A"), row("B"), row("C")])
    assert len(available()) == 3
    result = observe([row("A", visible=False), row("B", uiUrl="malformed"), row("C")])
    assert result["quarantined"] == 1
    assert set(available()) == {identity("C")}
    assert set(r["app"]["id"] for r in offline[3]("thermal")) == {identity("C")}
    # Invalid metadata cannot preserve an old published projection for the same App.
    observe([row("C", visible=False, uiUrl="malformed")])
    assert not available()
    assert store_sync.status(STORE)["known"] == 3
    with storage.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM catalog_apps WHERE source_store_id=%s "
                "AND source_app_id = ANY(%s)",
                (STORE, ["A", "B", "C"]),
            ).fetchone()["n"]
            == 3
        )


def test_absence_empty_duplicate_and_return_do_not_invent_upstream_deletion(offline):
    observe([row("A"), row("B")])
    before = deepcopy(available()[identity("B")])
    observe([row("A")])
    assert set(available()) == {identity("A")}
    observe([])
    assert not available()
    observe([row("A"), row("A")])
    assert not available()
    observe([row("B")])
    after = available()[identity("B")]
    assert after["revision"] == before["revision"] and after["payload"] == before["payload"]
    assert store_sync.status(STORE)["snapshot_complete"] is False


def test_auth_failure_preserves_dated_observation_and_is_distinct_from_empty(offline):
    observe([row("A")])
    previous = store_sync.status(STORE)
    store_sync.failed(STORE, 401)
    state = store_sync.status(STORE)
    assert state["state"] == "authorization_required"
    assert state["snapshot_at"] == previous["snapshot_at"]
    assert state["last_success_at"] == previous["last_success_at"]
    assert state["available"] == 1
    observe([])
    assert store_sync.status(STORE)["state"] == "observed_api"
    assert not available()


def test_derived_index_recovers_and_removes_unavailable_stale_points(offline):
    client, collection, *_ = offline
    observe([row("A", readme="<p>qualifications remain intact.</p>"), row("B")])
    repair_store_index(STORE, client, indexer, collection)
    assert client.count(collection, exact=True).count == 2
    assert store_sync.status(STORE)["index_pending"] == 0
    observe([row("A", readme="Current source revision; simulator restrictions remain."), row("B")])
    assert store_sync.status(STORE)["index_pending"] == 1
    repair_store_index(STORE, client, indexer, collection)
    point = client.retrieve(collection, [indexer._app_id_to_int(identity("A"))], with_payload=True)[
        0
    ]
    assert (
        point.payload["source_evidence"]["readme"]
        == "Current source revision; simulator restrictions remain."
    )
    observe([row("B")])
    # Stored stale vector exists, but authoritative hydration already hides A.
    assert identity("A") not in {r["app"]["id"] for r in offline[3]("thermal")}
    repair_store_index(STORE, client, indexer, collection)
    assert client.count(collection, exact=True).count == 1
    client.delete_collection(collection)
    repair_store_index(STORE, client, indexer, collection)
    assert client.count(collection, exact=True).count == 1
    observe([row("A"), row("B")])
    repair_store_index(STORE, client, indexer, collection)
    assert client.count(collection, exact=True).count == 2


def test_browser_catalogue_covers_all_observed_apps_and_gates_unavailable(offline):
    observe([row(f"App-{i:03}") for i in range(63)] + [row("unpublished", visible=False)])

    def catalogue(ids):
        rows = available()
        return [
            StoreAppMetadata.model_validate(r["payload"]).recommendation_projection()
            for r in rows.values()
        ]

    playground = SimpleNamespace(
        catalogue=catalogue,
        records=[],
        chat=SimpleNamespace(
            delete_session_v2=lambda session_id: {}, submit_recommendation_event=lambda: {}
        ),
    )
    with TestClient(create_app(playground), base_url="http://127.0.0.1:8098") as browser:
        pages = [browser.get(f"/api/v2/catalogue?offset={offset}").json() for offset in (0, 25, 50)]
        ids = [r["app_id"] for p in pages for r in p["apps"]]
        assert len(ids) == len(set(ids)) == 63
        assert pages[-1]["next_offset"] is None
        assert all(p["total"] == 63 for p in pages)
        assert browser.get("/api/v2/catalogue?limit=51").status_code == 422
        observe([row("App-000")])
        assert browser.get("/api/v2/catalogue").json()["total"] == 1
        assert (
            browser.post(
                "/evaluation/refresh", headers={"origin": "https://attacker.invalid"}
            ).status_code
            == 403
        )


def test_index_failure_retains_pending_work_and_lexical_retrieval(offline, monkeypatch):
    client, collection, *_ = offline
    observe([row("A")])
    upsert = client.upsert

    def unavailable(*args, **kwargs):
        raise RuntimeError("isolated vector write unavailable")

    monkeypatch.setattr(client, "upsert", unavailable)
    with pytest.raises(RuntimeError):
        repair_store_index(STORE, client, indexer, collection)
    assert store_sync.status(STORE)["index_pending"] == 1
    assert identity("A") in {r["app"]["id"] for r in offline[3]("thermal")}
    monkeypatch.setattr(client, "upsert", upsert)
    repair_store_index(STORE, client, indexer, collection)
    assert store_sync.status(STORE)["index_pending"] == 0

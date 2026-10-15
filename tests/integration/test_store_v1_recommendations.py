"""Offline normalization → PostgreSQL → disposable Qdrant → recommendation pipeline.

All records are invented. Embeddings are deterministic; no LLM or Store is contacted.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import ModuleType
from unittest.mock import MagicMock
from urllib.parse import urlparse

import pytest
from hedge_shared import storage
from hedge_shared.models_v2 import SearchFilters
from hedge_shared.store_v1 import StoreAppMetadata
from qdrant_client import QdrantClient, models

from .test_catalogue_snapshot import wait_for_blocked_lock
from .test_index_consistency import indexer, ingest, searcher
from .test_store_v1_persistence import database as database
from .test_store_v1_persistence import migrate, rows

ROOT = Path(__file__).parents[2]
RAW = json.loads((ROOT / "tests/fixtures/store-v1/offline-recommendations.json").read_text())
client_module = importlib.import_module(ingest.__package__.rsplit(".", 1)[0] + ".client")
snapshot = importlib.import_module(ingest.__package__.rsplit(".", 1)[0] + ".snapshot")
package = ModuleType("offline_store_recommend")
package.__path__ = [str(ROOT / "services/expert-recommend/app")]
sys.modules[package.__name__] = package
recommender = importlib.import_module(package.__name__ + ".recommender")
STORE = "Offline-Store"


@pytest.fixture
def offline(database, monkeypatch):
    migrate.main()
    for store in (STORE, "Other-Store"):
        result = snapshot.reconcile_catalogue_snapshot(
            "offline-fixtures", lambda store=store: [r for r in RAW if r["fkAppStoreId"] == store],
            store_id=store,
        )
        assert result["quarantined"] == 0
    url = os.getenv("HEDGE_TEST_QDRANT_URL")
    if not url:
        pytest.skip("requires explicitly isolated HEDGE_TEST_QDRANT_URL")
    assert urlparse(url).hostname == "vectors"
    client = QdrantClient(url=url, check_compatibility=False, timeout=3)
    collection = "hedge_store_offline_" + uuid.uuid4().hex
    client.create_collection(
        collection, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE)
    )
    llm = MagicMock(side_effect=AssertionError("Store explanations must not call an LLM"))
    monkeypatch.setattr(recommender, "OllamaClient", llm)
    monkeypatch.setattr(searcher, "_cache", MagicMock(side_effect=AssertionError("offline cache")))

    def search(query="energy", *, locale="en", filters=None, limit=10):
        return searcher.search_apps_v2(
            client, query=query, locale=locale, filters=filters or SearchFilters(), limit=limit,
            store_id=STORE, collection_name=collection,
        )

    monkeypatch.setattr(
        recommender, "_search_apps_v2",
        lambda query, *, locale, filters, limit: search(
            query, locale=locale, filters=SearchFilters.model_validate(filters), limit=limit,
        ),
    )
    app = client_module.normalize_store_v1_app(RAW[0])
    yield client, collection, app, search, llm
    client.delete_collection(collection)
    client.close()


def operation(app, revision=1, kind="upsert"):
    return {
        "app_id": app.id, "revision": revision, "operation": kind,
        "app": app.model_dump(mode="json", exclude={"checksum", "id", "public_eligible"})
        if kind == "upsert" else None,
    }


def apply(offline, *operations):
    client, collection, *_ = offline
    return indexer.apply_operations(
        client, list(operations), store_id=STORE, collection_name=collection,
    )


def save(app):
    return storage.upsert_catalogue_app(storage.create_ingestion_run("offline-fixtures"), app)


def payload(offline, app):
    client, collection, *_ = offline
    points = client.retrieve(collection, [indexer._app_id_to_int(app.id)], with_payload=True)
    return points[0].payload if points else None


def test_offline_pipeline_keeps_native_identity_sparse_facts_and_grounded_explanations(offline):
    client, collection, app, search, llm = offline
    assert apply(offline, operation(app)) == 1
    result = recommender.recommend_v2(query="energy", locale="pt", filters={}, limit=10)
    assert len(result["apps"]) == 1 and len(result["candidates"]) == 1
    assert result["apps"][0]["app"]["app_id"] == "Sparse-App"
    assert result["candidates"][0]["app"]["app_id"] == "Shared-App"
    by_native = {r["app"]["app_id"]: r for r in [*result["apps"], *result["candidates"]]}
    returned = by_native[app.app_id]
    assert returned["app"]["id"] == app.id and returned["app"]["store_id"] == STORE
    assert returned["app"]["public_eligible"] is True
    sparse = by_native["Sparse-App"]["app"]
    assert sparse["name"] is sparse["provider"] is None
    assert sparse["description"] == "Energy readings."
    assert "Empty-App" not in by_native
    for row in [*result["apps"], *result["candidates"]]:
        assert not {"score", "relevance"} & row.keys()
        assert not {"title", "summary", "capabilities", "categories", "supported_languages",
                    "semantic_annotations", "readme", "dataspaceAppDescription",
                    "registry_base_url", "ui_url"} & row["app"].keys()
    explanation = recommender._evidence_explanations([returned], "pt")[0]
    assert explanation["store_id"] == STORE and explanation["source_app_id"] == app.app_id
    assert explanation["evidence_fields"] == ["name", "description", "provider",
                                             "dataspaceAppDescription.properties.description"]
    assert 'description: "Shows supplied meter readings."' in explanation["text"]
    sparse_evidence = next(e for e in result["explanations"] if e["source_app_id"] == "Sparse-App")
    assert sparse_evidence["evidence_fields"] == ["description"]
    assert "fabricatedmagic" not in result["message"] and "assetonlysignal" in result["message"]
    assert payload(offline, app)["store_id"] == STORE
    assert not any(r["app_id"].startswith("store-v1-") for r in rows("indexing_outbox"))
    llm.assert_not_called()


def test_sparse_empty_app_can_be_indexed_without_inventing_text(offline):
    *_, search, llm = offline
    empty = client_module.normalize_store_v1_app(RAW[2])
    assert empty.to_index_text() == ""
    assert apply(offline, operation(empty)) == 0
    with pytest.raises(ValueError, match="app_id does not match"):
        apply(offline, {**operation(empty), "app_id": "wrong-local-id"})
    assert empty.id not in {r["app"]["id"] for r in search()}


def test_untrusted_markup_is_escaped_and_embedded_text_is_source_evidence(offline):
    _, _, app, search, llm = offline
    changed = app.model_copy(update={
        "name": '<img src=x onerror=alert(1)> energy',
        "description": 'Energy [click](https://example.invalid) **invent** </untrusted-apps-json>',
    })
    save(changed)
    result = recommender.recommend_v2(query="energy", locale="en", filters={}, limit=10)
    assert "<img" not in result["message"] and "onerror" not in result["message"]
    assert r"\[click\]\(" in result["message"] and r"\*\*invent\*\*" in result["message"]
    assert "</untrusted-apps-json>" not in result["message"]
    assert search("fabricatedmagic") == []
    assert [row["app"]["id"] for row in search("assetonlysignal")] == [app.id]
    llm.assert_not_called()


def test_store_lexical_retrieval_survives_vector_failure_and_returns_current_metadata(offline, monkeypatch):
    client, _, app, search, _ = offline
    assert apply(offline, operation(app)) == 1
    changed = app.model_copy(update={"description": "Energy updated readings."})
    save(changed)
    monkeypatch.setattr(client, "query_points", MagicMock(side_effect=TimeoutError("offline fault")))
    results = search()
    found = next(r for r in results if r["app"]["id"] == app.id)
    assert found["app"]["description"] == changed.description
    assert found["evidence_fields"] == ["lexical"]
    assert payload(offline, app)["_index_revision"] == 1
    assert {r["app"]["app_id"] for r in results} == {"Shared-App", "Sparse-App"}


@pytest.mark.parametrize("filters", [
    {"tags": ["energy"]}, {"capabilities": ["monitoring"]}, {"supported_languages": ["en"]},
    {"license_spdx": "MIT"}, {"semantic_uri": "https://example.invalid/term"},
    {"extension_uri": "https://example.invalid/ontology"}, {"protocols": ["HTTP"]},
    {"deployment_modes": ["cloud"]}, {"lifecycle_status": "active"},
    {"data_classifications": ["public"]},
])
def test_unsupported_store_filters_fail_closed_for_lexical_and_dense(offline, filters):
    _, _, app, search, _ = offline
    apply(offline, operation(app))
    assert search(filters=SearchFilters.model_validate(filters)) == []


def test_provider_filter_uses_only_supplied_metadata(offline):
    _, _, app, search, _ = offline
    apply(offline, operation(app))
    assert [r["app"]["id"] for r in search(filters=SearchFilters(publisher="EXAMPLE"))] == [app.id]
    assert search(filters=SearchFilters(publisher="missing")) == []


def test_stale_operations_and_withdrawal_reappearance_preserve_authority(offline):
    _, _, app, search, _ = offline
    apply(offline, operation(app))
    withdrawn = app.model_copy(update={"visible": False})
    save(withdrawn)
    assert app.id not in {r["app"]["id"] for r in search()}
    assert apply(offline, operation(app)) == 0
    assert apply(offline, operation(withdrawn, 2, "delete")) == 1
    assert payload(offline, app) is None
    save(app)
    assert apply(offline, operation(app, 3), operation(withdrawn, 2, "delete")) == 1
    assert payload(offline, app)["_index_revision"] == 3
    assert app.id in {r["app"]["id"] for r in search()}
    with pytest.raises(ValueError, match="authoritative revision"):
        apply(offline, operation(app.model_copy(update={"provider": "tampered"}), 3))


def test_absence_retirement_is_checked_even_when_payload_flags_remain_true(offline):
    _, _, app, search, _ = offline
    apply(offline, operation(app))
    snapshot.reconcile_catalogue_snapshot(
        "offline-fixtures", lambda: [RAW[1]], store_id=STORE, snapshot_complete=True,
    )
    assert payload(offline, app)["public_eligible"] is True  # Stale derived fact.
    assert app.id not in {r["app"]["id"] for r in search()}
    assert apply(offline, operation(app, 2, "delete")) == 1


def test_store_scope_cannot_index_another_store_or_enter_public_reads(offline, database):
    client, _, app, search, _ = offline
    other = client_module.normalize_store_v1_app(RAW[-1])
    assert other.app_id == app.app_id and other.id != app.id
    with pytest.raises(ValueError, match="offline Store"):
        apply(offline, operation(other))
    assert apply(offline, operation(other, 1, "delete")) == 0
    assert storage.get_catalogue_app(app.id) is None
    assert app.id not in storage.get_catalogue_apps([app.id])
    total, listed = storage.list_catalogue_apps(limit=100, offset=0)
    assert total == 1 and listed[0]["id"] == database.id
    assert all(r["id"] == database.id for r in storage.lexical_search(
        "energy", locale="en", filters=SearchFilters(), limit=20,
    ))
    with pytest.raises(ValueError):
        indexer.apply_operations(client, [operation(app)])
    assert indexer.apply_operations(client, [operation(app, 1, "delete")]) == 0


def test_store_search_fails_closed_when_postgresql_authority_is_unavailable(offline, monkeypatch):
    _, _, app, search, _ = offline
    apply(offline, operation(app))
    monkeypatch.setattr(searcher, "get_catalogue_apps", MagicMock(side_effect=ConnectionError("DB")))
    with pytest.raises(ConnectionError):
        search()


def test_stream_uses_the_same_grounded_store_explanations(offline):
    result = recommender.recommend_v2(query="energy", locale="en", filters={}, limit=5)
    events = list(recommender.recommend_v2_stream(query="energy", locale="en", filters={}, limit=5))
    assert events[0]["apps"] == result["apps"]
    assert "".join(e["content"] for e in events if e["type"] == "explanation_delta") == result["message"]
    assert events[-1]["explanations"] == result["explanations"]


def test_store_catalogue_update_serializes_with_current_index_write(offline, monkeypatch):
    client, _, app, _, _ = offline
    started, release = Event(), Event()
    real = client.upsert

    def blocked(**kwargs):
        started.set()
        assert release.wait(5)
        return real(**kwargs)

    monkeypatch.setattr(client, "upsert", blocked)
    changed = app.model_copy(update={"description": "Energy newer metadata."})
    with ThreadPoolExecutor(2) as pool:
        indexed = pool.submit(apply, offline, operation(app))
        assert started.wait(5)
        updated = pool.submit(save, changed)
        try:
            wait_for_blocked_lock("transactionid")
            assert not updated.done()
        finally:
            release.set()
        assert indexed.result(timeout=5) == 1
        assert updated.result(timeout=5) == "updated"
    monkeypatch.setattr(client, "upsert", real)
    assert apply(offline, operation(changed, 2), operation(app)) == 1
    assert payload(offline, app)["_index_revision"] == 2


def test_public_search_rejects_store_vectors_even_if_they_leak_into_its_collection(
    offline, database, monkeypatch,
):
    client, collection, app, _, _ = offline
    apply(offline, operation(app))
    monkeypatch.setattr(searcher, "COLLECTION_ALIAS", collection)
    results = searcher.search_apps_v2(
        client, query="energy", locale="en", filters=SearchFilters(), limit=10,
    )
    assert [r["app"]["id"] for r in results] == [database.id]


@pytest.mark.parametrize("missing", ["store_id", "collection_name"])
def test_offline_scope_is_required_before_any_database_or_vector_io(offline, missing, monkeypatch):
    client, collection, app, _, _ = offline
    args = {"store_id": STORE, "collection_name": collection}
    args.pop(missing)
    with monkeypatch.context() as scoped:
        scoped.setattr(storage, "connection", MagicMock(side_effect=AssertionError("no DB IO")))
        scoped.setattr(client, "query_points", MagicMock(side_effect=AssertionError("no vector IO")))
        with pytest.raises(ValueError, match="disposable collection"):
            indexer.apply_operations(client, [operation(app)], **args)
        with pytest.raises(ValueError, match="disposable collection"):
            searcher.search_apps_v2(
                client, query="energy", locale="en", filters=SearchFilters(), limit=10, **args,
            )


def test_store_metadata_survives_transport_persistence_index_and_recommendation(offline, monkeypatch):
    """Exercise the actual Store client and service functions, without private data."""
    import httpx

    raw = json.loads((ROOT / "tests/fixtures/store-v1/metadata-app.json").read_text())
    api = client_module.HedgeApiClient(
        "https://store.invalid/backend/api/v1", store_id=STORE, token="test-only",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[raw])),
    )
    report = snapshot.reconcile_catalogue_snapshot(
        "metadata-contract-fixture", api.fetch_all_apps, store_id=STORE,
        snapshot_complete=api.snapshot_complete,
    )
    assert report["quarantined"] == 0
    app = client_module.normalize_store_v1_app(raw)
    stored = storage.get_catalogue_apps([app.id], store_id=STORE)[app.id]
    assert StoreAppMetadata.model_validate(stored["payload"]).checksum == app.checksum
    assert stored["payload"]["dataspace_app_description"] == raw["dataspaceAppDescription"]
    assert stored["payload"]["readme"] == raw["readme"]
    assert apply(offline, operation(app)) == 1
    assert payload(offline, app)["built_for_connector"] == "ExampleConnector"
    _, _, _, search, _ = offline
    for query in ("MQTT", "forecasting", "prediction", "ExampleConnector"):
        result = recommender.recommend_v2(query=query, locale="en", filters={}, limit=5)
        found_row = next(r for r in [*result["apps"], *result["candidates"]] if r["app"]["id"] == app.id)
        found = found_row["app"]
        assert (found_row in result["apps"]) is (query != "ExampleConnector")
        # Connector association remains retrievable, never a capability guarantee.
        assert found["billable"] is False and found["price"] == 0
        assert found["versions"][0]["version"] == "2.0"
        assert "source_evidence" in found and "readme" not in found
        explanation = recommender._evidence_explanations([found_row], "en")[0]
        assert "readme" in explanation["evidence_fields"]
        assert "dataspaceAppDescription.properties.featureList[0]" in explanation["evidence_fields"]
        assert 'billable: "false"' in explanation["text"]
        assert "UNVERIFIED" not in result["message"] and "fabricatedmagic" not in result["message"]
    # New evidence works via PostgreSQL when vectors fail, using current revisions.
    monkeypatch.setattr(offline[0], "query_points", MagicMock(side_effect=TimeoutError("offline")))
    assert [row["app"]["id"] for row in search("MQTT")] == [app.id]
    changed = app.model_copy(update={"built_for_connector": "ReplacementConnector"})
    assert save(changed) == "updated"
    assert [row["app"]["built_for_connector"] for row in search("ReplacementConnector")] == [
        "ReplacementConnector"
    ]
    assert search("ExampleConnector") == []
    assert storage.get_catalogue_app(app.id) is None
    assert not any(row["app_id"] == app.id for row in rows("indexing_outbox"))
    save(changed.model_copy(update={"visible": False}))
    assert search("MQTT") == []


@pytest.mark.parametrize("length", [1254, 16001])
def test_readme_output_limits_preserve_current_store_metadata_and_streaming(offline, length):
    start = "Specification notes: "
    end = " MQTT is supported only in simulation; production does not support MQTT."
    readme = start + "x" * (length - len(start) - len(end)) + end
    app = client_module.normalize_store_v1_app({
        "appId": "Output-Limit-App", "fkAppStoreId": STORE, "name": "Boundary evidence",
        "description": "Shows supplied telemetry.", "readme": readme,
        "active": True, "visible": True,
    })
    save(app)
    stored = storage.get_catalogue_apps([app.id], store_id=STORE)[app.id]
    assert stored["payload"]["readme"] == readme
    assert stored["revision"] == 1
    assert apply(offline, operation(app)) == 1
    result = recommender.recommend_v2(query="telemetry", locale="en", filters={}, limit=5)
    row = next(row for row in result["apps"] if row["app"]["id"] == app.id)
    assert row["app"]["store_id"] == STORE and row["app"]["app_id"] == app.app_id
    explanation = next(e for e in result["explanations"] if e["app_id"] == app.id)
    assert 'description: "Shows supplied telemetry."' in explanation["text"]
    assert "MQTT is supported" not in explanation["text"]
    assert "supplied no descriptive metadata" not in explanation["text"]
    if length == 1254:
        assert row["app"]["source_evidence"]["readme"] == readme
        assert "readme: complete quotation omitted" in explanation["text"]
    else:
        assert row["app"]["readme_status"] == "too_large"
        assert "readme" not in row["app"]["source_evidence"]
        assert "too large" in explanation["text"]
    events = list(recommender.recommend_v2_stream(query="telemetry", locale="en", filters={}, limit=5))
    assert events[0]["apps"] == result["apps"]
    assert "".join(e["content"] for e in events if e["type"] == "explanation_delta") == result["message"]
    assert events[-1]["explanations"] == result["explanations"]
    assert not any(row["app_id"] == app.id for row in rows("indexing_outbox"))
    save(app.model_copy(update={"visible": False}))
    assert app.id not in {row["app"]["id"] for row in recommender.recommend_v2(
        query="telemetry", locale="en", filters={}, limit=5,
    )["apps"]}


@pytest.mark.parametrize("description", ["Earthquake warnings.", "Earthquake warnings only in simulation."])
def test_disposable_store_pipeline_separates_dense_neighbours_from_source_supported_apps(offline, description):
    water = client_module.normalize_store_v1_app({
        "appId": "Water-Meter", "fkAppStoreId": STORE, "name": "Water Meter",
        "description": "Displays water readings.", "active": True, "visible": True,
    })
    warning = client_module.normalize_store_v1_app({
        "appId": "Warning-App", "fkAppStoreId": STORE,
        "description": description, "active": True, "visible": True,
    })
    for app in (water, warning):
        save(app)
        assert apply(offline, operation(app)) == 1
    result = recommender.recommend_v2(query="earthquake warnings", locale="en", filters={}, limit=10)
    supported = "simulation" not in description
    assert [r["app"]["id"] for r in result["apps"]] == ([warning.id] if supported else [])
    by_id = {r["app"]["id"]: r for r in result["candidates"]}
    assert by_id[water.id]["evidence_fields"] == ["dense"]
    assert by_id[water.id]["suitability"]["status"] == "uncertain"
    assert result["decision"]["outcome"] == ("recommended" if supported else "abstained")
    assert "highest-ranked" not in result["message"] and "Start with" not in result["message"]
    assert water.description in result["message"]
    all_rows = [*result["apps"], *result["candidates"]]
    returned = next(r for r in all_rows if r["app"]["id"] == warning.id)
    assert returned["app"]["store_id"] == STORE and returned["app"]["app_id"] == warning.app_id
    assert returned["app"]["source_evidence"]["description"] == description
    assert storage.get_catalogue_apps([warning.id], store_id=STORE)[warning.id]["revision"] == 1
    events = list(recommender.recommend_v2_stream(query="earthquake warnings", locale="en", filters={}, limit=10))
    assert events[0]["apps"] == result["apps"] and events[0]["candidates"] == result["candidates"]
    assert "".join(e["content"] for e in events if e["type"] == "explanation_delta") == result["message"]
    # Current PostgreSQL visibility remains authoritative over stale vector evidence.
    save(warning.model_copy(update={"visible": False}))
    withdrawn = recommender.recommend_v2(query="earthquake warnings", locale="en", filters={}, limit=10)
    assert withdrawn["apps"] == []
    assert warning.id not in {r["app"]["id"] for r in withdrawn["candidates"]}
    assert payload(offline, warning)["_index_revision"] == 1


@pytest.mark.parametrize(('description', 'readme', 'query', 'locale', 'supported'), [
    ('Earthquake warnings are planned for a future release.', None, 'earthquake warnings', 'en', False),
    ('Earthquake warnings. They are not supported by this App.', None, 'earthquake warnings', 'en', False),
    ('Provides earthquake warnings.', 'This feature is disabled. It cannot be used.', 'earthquake warnings', 'en', False),
    ('Provides earthquake warnings if sensors are installed.', None, 'earthquake warnings', 'en', False),
    ('Provides earthquake warnings. Sends them via SMS.', None, 'earthquake warnings SMS', 'en', True),
    ('Provides earthquake warnings and water readings. Sends them via SMS.', None, 'earthquake warnings SMS', 'en', False),
    ('Provides earthquake warnings. Another App sends them via SMS.', None, 'earthquake warnings SMS', 'en', False),
    ('Provides earthquake warnings.', 'Delivers earthquake warnings via SMS.', 'earthquake warnings SMS', 'en', True),
    ('Provides earthquake warnings.', 'MQTT is unavailable.', 'earthquake warnings', 'en', True),
    ('Não envia alertas de terremoto.', None, 'alertas de terremoto', 'pt', False),
    ('Envia alertas de terremoto.', None, 'Preciso de apps para alertas de terremoto', 'pt', True),
    ('Unterstützt MQTT nicht.', None, 'MQTT', 'de', False),
    ('Unterstützt MQTT.', None, 'Ich brauche eine App für MQTT', 'de', True),
])
def test_coherent_claims_survive_real_store_boundaries(offline, description, readme, query, locale, supported):
    app = client_module.normalize_store_v1_app({
        'appId': 'Claim-Review-App', 'fkAppStoreId': STORE, 'name': 'Review App',
        'description': description, 'readme': readme, 'active': True, 'visible': True,
    })
    save(app)
    assert apply(offline, operation(app)) == 1
    stored = storage.get_catalogue_apps([app.id], store_id=STORE)[app.id]
    assert stored['revision'] == 1
    assert stored['payload']['description'] == description and stored['payload']['readme'] == readme
    assert StoreAppMetadata.model_validate(stored['payload']).checksum == app.checksum
    result = recommender.recommend_v2(query=query, locale=locale, filters={}, limit=10)
    # Prove absence from apps is a decision, rather than a retrieval failure.
    row = next(r for r in [*result['apps'], *result['candidates']] if r['app']['id'] == app.id)
    assert (row in result['apps']) is supported
    assert row['app']['store_id'] == STORE and row['app']['app_id'] == app.app_id
    assert row['app']['source_evidence']['description'] == description
    assert row['suitability']['status'] == ('source_supported' if supported else 'uncertain')
    events = list(recommender.recommend_v2_stream(query=query, locale=locale, filters={}, limit=10))
    assert events[0]['apps'] == result['apps'] and events[0]['candidates'] == result['candidates']
    assert events[0]['decision'] == result['decision']
    assert ''.join(e['content'] for e in events if e['type'] == 'explanation_delta') == result['message']
    # A stale vector cannot keep an App in either output collection after withdrawal.
    save(app.model_copy(update={'visible': False}))
    withdrawn = recommender.recommend_v2(query=query, locale=locale, filters={}, limit=10)
    assert app.id not in {r['app']['id'] for r in [*withdrawn['apps'], *withdrawn['candidates']]}
    assert payload(offline, app)['_index_revision'] == 1


@pytest.mark.parametrize('case', json.loads(
    (ROOT / 'tests/fixtures/store-v1/suitability-ownership.json').read_text()
), ids=lambda case: case['case'])
def test_owned_evidence_survives_store_persistence_and_retrieval(offline, case):
    source = case['source']
    app = client_module.normalize_store_v1_app({
        'appId': 'Ownership-App', 'fkAppStoreId': STORE, 'name': 'Review App',
        'description': source['description'], 'readme': source.get('readme'),
        'dataspaceAppDescription': source.get('dataspace_app_description'),
        'active': True, 'visible': True,
    })
    save(app)
    assert apply(offline, operation(app)) == 1
    stored = storage.get_catalogue_apps([app.id], store_id=STORE)[app.id]
    assert stored['revision'] == 1
    assert StoreAppMetadata.model_validate(stored['payload']).checksum == app.checksum
    for key, value in source.items():
        assert stored['payload'][key] == value
    args = {'query': case['query'], 'locale': case['locale'], 'filters': {}, 'limit': 10}
    result = recommender.recommend_v2(**args)
    row = next(r for r in [*result['apps'], *result['candidates']] if r['app']['id'] == app.id)
    assert (row in result['apps']) is case['supported']
    assert row['app']['store_id'] == STORE and row['app']['app_id'] == 'Ownership-App'
    assert row['app']['source_evidence']['description'] == source['description']
    assert row['suitability']['status'] == ('source_supported' if case['supported'] else 'uncertain')
    events = list(recommender.recommend_v2_stream(**args))
    assert events[0]['apps'] == result['apps'] and events[0]['candidates'] == result['candidates']
    assert events[0]['decision'] == result['decision']
    assert ''.join(e['content'] for e in events if e['type'] == 'explanation_delta') == result['message']
    save(app.model_copy(update={'visible': False}))
    withdrawn = recommender.recommend_v2(**args)
    assert app.id not in {r['app']['id'] for r in [*withdrawn['apps'], *withdrawn['candidates']]}
    assert payload(offline, app)['_index_revision'] == 1

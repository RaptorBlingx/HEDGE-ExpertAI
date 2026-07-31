"""Focused tests for independent retrieval, filters, cache, and RRF."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hedge_shared.models_v2 import SearchFilters

ROOT = Path(__file__).parents[2]
APP_DIR = ROOT / "services" / "discovery-ranking" / "app"

package = types.ModuleType("dr_v2_app")
package.__path__ = [str(APP_DIR)]
package.__package__ = "dr_v2_app"
sys.modules["dr_v2_app"] = package

embeddings = types.ModuleType("dr_v2_app.embeddings")
embeddings.encode_single = MagicMock(return_value=[0.1] * 384)
sys.modules["dr_v2_app.embeddings"] = embeddings

indexer = types.ModuleType("dr_v2_app.indexer")
indexer.COLLECTION_ALIAS = "hedge_apps_current"
sys.modules["dr_v2_app.indexer"] = indexer

spec = importlib.util.spec_from_file_location(
    "dr_v2_app.searcher_v2",
    APP_DIR / "searcher_v2.py",
    submodule_search_locations=[],
)
module = importlib.util.module_from_spec(spec)
module.__package__ = "dr_v2_app"
assert spec.loader is not None
spec.loader.exec_module(module)
sys.modules["dr_v2_app.searcher_v2"] = module


@pytest.fixture(scope="module")
def payload() -> dict:
    records = json.loads(
        (ROOT / "services/mock-api/app/data/apps-v2.json").read_text(encoding="utf-8")
    )
    return records[0]


def test_dense_filter_accepts_complete_matching_profile(payload: dict) -> None:
    annotation = payload["semantic_annotations"][0]
    contract = payload["inputs"][0]
    filters = SearchFilters(
        publisher=payload["publisher"]["name"].split()[0],
        lifecycle_status=payload["lifecycle"]["status"],
        license_spdx=payload["trust"]["license_spdx"],
        tags=[payload["tags"][0]],
        capabilities=[payload["capabilities"][0]],
        protocols=[payload["protocols"][0]],
        supported_languages=["en", "de"],
        deployment_modes=[payload["deployment"]["modes"][0]],
        semantic_uri=annotation["term_uri"],
        extension_uri=annotation["ontology_uri"],
        data_classifications=[contract["data_classification"]],
    )
    assert module._matches_filters(payload, filters)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publisher", "not this publisher"),
        ("lifecycle_status", "deprecated"),
        ("license_spdx", "GPL-3.0-only"),
        ("tags", ["missing"]),
        ("capabilities", ["missing"]),
        ("protocols", ["missing"]),
        ("supported_languages", ["tr", "de", "fr", "es", "it", "nl", "pt", "en"]),
        ("deployment_modes", ["saas"]),
        ("semantic_uri", "https://saref.etsi.org/core/Missing"),
        ("extension_uri", "https://saref.etsi.org/saref4grid/"),
        ("data_classifications", ["restricted"]),
    ],
)
def test_dense_filter_rejects_non_matching_values(
    payload: dict,
    field: str,
    value: object,
) -> None:
    candidate = deepcopy(payload)
    if field == "supported_languages":
        candidate["supported_languages"] = ["en"]
    assert not module._matches_filters(candidate, SearchFilters(**{field: value}))


def test_dense_candidates_discard_old_schema_and_filter_miss(payload: dict) -> None:
    old = MagicMock(score=0.99, payload={**payload, "schema_version": "1.0"})
    miss = MagicMock(score=0.98, payload={**payload, "protocols": ["OPC UA"]})
    good = MagicMock(score=0.9, payload=payload)
    response = MagicMock(points=[old, miss, good])
    client = MagicMock()
    client.query_points.return_value = response

    results = module._dense_candidates(
        client,
        "solar energy",
        filters=SearchFilters(protocols=[payload["protocols"][0]]),
        limit=1,
    )

    assert [item["id"] for item in results] == [payload["id"]]
    assert results[0]["dense_score"] == 0.9
    assert client.query_points.call_args.kwargs["collection_name"] == "hedge_apps_current"


def test_rrf_is_deterministic_bounded_and_strips_internal_payload(payload: dict) -> None:
    app = {**deepcopy(payload), "_index_revision": 7}
    annotation = app["semantic_annotations"][0]
    annotation.update({"provenance": "curated", "review_status": "approved", "reviewed_at": "2026-07-31T00:00:00Z"})
    filters = SearchFilters(extension_uri=annotation["ontology_uri"])

    results = module.reciprocal_rank_fusion(
        [{"id": app["id"], "payload": app, "dense_score": 0.8}],
        [{"id": app["id"], "payload": app, "lexical_score": 0.5}],
        filters=filters,
        limit=5,
    )

    assert len(results) == 1
    assert results[0]["rank"] == 1
    assert results[0]["relevance"] == "high"
    assert results[0]["evidence_fields"] == ["dense", "lexical"]
    assert "_index_revision" not in results[0]["app"]
    assert module._semantic_boost(app, filters) == module.SEMANTIC_BOOST_MAX
    assert module._semantic_boost(app, SearchFilters()) == 0.0


def test_search_uses_revisioned_cache(payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    cache = MagicMock()
    cache.get.return_value = None
    monkeypatch.setattr(module, "_cache", lambda: cache)
    monkeypatch.setattr(
        module,
        "lexical_search",
        lambda *args, **kwargs: [{"id": payload["id"], "payload": payload}],
    )
    monkeypatch.setattr(module, "_dense_candidates", lambda *args, **kwargs: [])

    first = module.search_apps_v2(
        MagicMock(),
        query="  SOLAR energy ",
        locale="en",
        filters=SearchFilters(),
        limit=2,
        catalogue_revision="revision-7",
    )
    assert first[0]["app"]["id"] == payload["id"]
    cache.setex.assert_called_once()
    assert "revision-7" in cache.get.call_args.args[0]

    cache.get.return_value = json.dumps(first)
    monkeypatch.setattr(
        module,
        "lexical_search",
        lambda *args, **kwargs: pytest.fail("cache hit must skip retrieval"),
    )
    assert module.search_apps_v2(
        MagicMock(),
        query="SOLAR energy",
        locale="en",
        filters=SearchFilters(),
        limit=2,
        catalogue_revision="revision-7",
    ) == first


def test_search_continues_when_cache_is_unavailable(
    payload: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = MagicMock()
    cache.get.side_effect = RuntimeError("cache down")
    cache.setex.side_effect = RuntimeError("cache down")
    monkeypatch.setattr(module, "_cache", lambda: cache)
    monkeypatch.setattr(
        module,
        "lexical_search",
        lambda *args, **kwargs: [{"id": payload["id"], "payload": payload}],
    )
    monkeypatch.setattr(module, "_dense_candidates", lambda *args, **kwargs: [])

    results = module.search_apps_v2(
        MagicMock(),
        query="energy",
        locale="en",
        filters=SearchFilters(),
        limit=1,
    )
    assert results[0]["app"]["id"] == payload["id"]

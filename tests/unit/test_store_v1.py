"""Offline contracts: Store v1 metadata must not acquire synthetic v2 facts."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from hedge_shared.models_v2 import AppMetadataV2
from hedge_shared.store_v1 import StoreAppMetadata
from pydantic import ValidationError

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location(
    "store_v1_client",
    ROOT / "services/metadata-ingest/app/client.py",
)
client = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(client)
normalize = client.normalize_store_v1_app
RECORDS = json.loads((ROOT / "tests/fixtures/store-v1/apps.json").read_text())
SAMPLED_SHAPES = json.loads(
    (ROOT / "tests/fixtures/store-v1/sanitized-observed-shapes.json").read_text()
)


def test_sparse_record_retains_only_known_identity() -> None:
    app = normalize(RECORDS[0])
    assert app.store_id == "Store-A" and app.app_id == "Shared-App"
    assert app.name is app.description is app.provider is app.readme is None
    assert app.registration_date is app.versions is app.ui_url is None
    assert app.active is app.visible is None
    assert not app.public_eligible and app.to_index_text() == ""
    payload = app.model_dump(mode="json")
    assert payload["source_profile"] == "hedge-store-v1"
    for field in (
        "schema_version",
        "license_spdx",
        "semantic_annotations",
        "supported_languages",
        "updated_at",
        "app_url",
        "summary",
        "lifecycle",
    ):
        assert field not in payload


def test_rich_record_maps_evidence_without_inferred_versions_or_links() -> None:
    app = normalize(RECORDS[1])
    assert app.public_eligible
    assert app.name == RECORDS[1]["name"] and app.provider == RECORDS[1]["provider"]
    assert str(app.ui_url) == RECORDS[1]["uiUrl"]
    assert str(app.openapi_url) == RECORDS[1]["openAPIURL"]
    assert app.registration_date.isoformat() == "2026-10-01T12:00:00+00:00"
    assert [v.version for v in app.versions] == ["2.0", "1.0"]
    assert app.description in app.to_index_text("pt")
    assert "Meter readings" in app.to_index_text("pt")
    assert "futureField" not in app.model_dump()
    assert "Unverified asset join" not in app.to_index_text()


def test_duplicate_app_ids_across_stores_are_distinct_and_stable() -> None:
    first, second = [normalize(raw) for raw in RECORDS[:2]]
    assert first.app_id == second.app_id and first.id != second.id
    assert first.id == normalize(dict(reversed(list(RECORDS[0].items())))).id
    assert first.id != normalize({**RECORDS[0], "fkAppStoreId": "store-a"}).id
    assert (
        normalize({"appId": "c", "fkAppStoreId": "a:b"}).id
        != normalize({"appId": "b:c", "fkAppStoreId": "a"}).id
    )


@pytest.mark.parametrize("active", [True, False, None])
@pytest.mark.parametrize("visible", [True, False, None])
def test_public_eligibility_requires_explicit_public_and_active(active, visible) -> None:
    app = normalize({**RECORDS[0], "active": active, "visible": visible})
    assert app.active is active and app.visible is visible
    assert app.public_eligible is (active is True and visible is True)
    assert not normalize(RECORDS[2]).public_eligible


def test_endpoint_store_context_supplies_missing_identity_but_cannot_override_it() -> None:
    assert normalize({"appId": "App"}, store_id="Store").store_id == "Store"
    assert normalize(RECORDS[0], store_id="Store-A").store_id == "Store-A"
    with pytest.raises(ValueError, match="conflicts"):
        normalize(RECORDS[0], store_id="Other")


@pytest.mark.parametrize(
    "field,value",
    [
        ("appId", None),
        ("appId", ""),
        ("appId", "  "),
        ("appId", " App "),
        ("appId", 7),
        ("fkAppStoreId", None),
        ("fkAppStoreId", ""),
        ("active", "true"),
        ("active", 1),
        ("visible", "false"),
        ("visible", 0),
        ("name", 123),
        ("description", {}),
        ("provider", {"name": "Publisher"}),
        ("uiUrl", "javascript:alert(1)"),
        ("openAPIURL", "bad-url"),
        ("registrationDate", 1750000000000.0),
        ("registrationDate", True),
        ("registrationDate", 10**30),
        ("registrationDate", "1750000000000"),
        ("registrationDate", "not-a-date"),
        ("registrationDate", "2026-10-01T12:00:00"),
        ("appVersionList", {}),
        ("appVersionList", [None]),
        ("appVersionList", [{"version": 2}]),
        ("appVersionList", [{"appVersionId": " "}]),
        ("appVersionList", [{"registrationDate": False}]),
        ("appVersionList", [{"fkAppId": "Another-App"}]),
        ("registryBaseURL", 123),
        ("registryBaseURL", {}),
    ],
)
def test_malformed_known_metadata_is_rejected_without_coercion(field, value) -> None:
    with pytest.raises(ValueError):
        normalize({**RECORDS[0], field: value})


@pytest.mark.parametrize("raw", [None, [], "app", 123, True])
def test_non_object_records_are_rejected(raw) -> None:
    with pytest.raises(ValueError, match="must be an object"):
        normalize(raw)


def test_optional_blanks_stay_missing_and_unknown_fields_do_not_affect_checksum() -> None:
    app = normalize({**RECORDS[0], "name": " ", "readme": "", "uiUrl": ""})
    assert app.name is app.readme is app.ui_url is None
    assert (
        normalize(RECORDS[0]).checksum
        == normalize(
            {**RECORDS[0], "newField": "future", "source_profile": "2.0", "visible_guess": True}
        ).checksum
    )
    assert app.checksum != normalize({**RECORDS[0], "visible": False}).checksum


def test_internal_v2_remains_strict_and_synthetic_transport_is_unchanged() -> None:
    fixtures = json.loads((ROOT / "services/mock-api/app/data/apps-v2.json").read_text())
    assert AppMetadataV2.model_validate(fixtures[0]).id == fixtures[0]["id"]
    with pytest.raises(ValidationError):
        AppMetadataV2.model_validate(normalize(RECORDS[1]).model_dump())
    broken = deepcopy(fixtures[0])
    del broken["trust"]
    with pytest.raises(ValidationError):
        AppMetadataV2.model_validate(broken)
    assert isinstance(client.get_client("https://mock.invalid"), client.MockApiClient)
    with patch.object(client.httpx, "get", side_effect=AssertionError("network call")):
        assert isinstance(normalize(RECORDS[0]), StoreAppMetadata)


def test_sanitized_observed_shapes_normalize_without_enrichment() -> None:
    first, second = [normalize(raw, store_id="Sample-Store") for raw in SAMPLED_SHAPES]
    assert first.registration_date == datetime(2026, 10, 1, 12, 0, 0, 123000, tzinfo=UTC)
    assert first.versions[0].registration_date == datetime(2026, 9, 1, 12, tzinfo=UTC)
    assert [v.version for v in first.versions] == ["1.0", "2.0"]
    assert first.registry_base_url == "registry.example.invalid/sample/app-a"
    assert first.readme == "<h2>Sample README</h2><p>Supplied HTML.</p>"
    assert first.public_eligible and not second.public_eligible
    assert second.registration_date is second.description is second.ui_url is None
    assert second.versions == [] and second.registry_base_url is None
    for raw, app in zip(SAMPLED_SHAPES, (first, second), strict=True):
        assert app.app_id == raw["appId"] and app.store_id == raw["fkAppStoreId"]
        assert app.dataspace_app_description == raw["dataspaceAppDescription"]
    assert "Unjoined asset" in first.to_index_text()
    for app in (first, second):
        payload = app.model_dump_json(exclude={"id", "public_eligible", "checksum"})
        assert StoreAppMetadata.model_validate_json(payload) == app


@pytest.mark.parametrize(
    "milliseconds,expected",
    [
        (0, "1970-01-01T00:00:00+00:00"),
        (-1, "1969-12-31T23:59:59.999000+00:00"),
        (1750000000, "1970-01-21T06:06:40+00:00"),
    ],
)
def test_integer_dates_always_use_milliseconds(milliseconds, expected) -> None:
    app = normalize({**RECORDS[0], "registrationDate": milliseconds})
    assert app.registration_date.isoformat() == expected


@pytest.mark.parametrize(
    "registry", ["registry.example.invalid:5000/team/app", "https://example.invalid/registry"]
)
def test_registry_locations_are_preserved_as_strings(registry) -> None:
    app = normalize({**RECORDS[0], "registryBaseURL": registry})
    assert type(app.registry_base_url) is str and app.registry_base_url == registry


@pytest.mark.parametrize(("store_id", "collection"), [
    ("Store", None), (None, "hedge_store_offline_" + "a" * 32),
    ("", "hedge_store_offline_" + "a" * 32),
    (" Store", "hedge_store_offline_" + "a" * 32),
    ("Store", "hedge_apps_current"), ("Store", "hedge_apps_v2"),
    ("Store", "hedge_store_offline_invalid"),
])
def test_offline_store_scope_cannot_target_public_collection(store_id, collection):
    from hedge_shared.store_v1 import validate_offline_store_scope

    with pytest.raises(ValueError, match="disposable collection"):
        validate_offline_store_scope(store_id, collection)


def test_offline_scope_is_not_a_public_search_request_option():
    from hedge_shared.models_v2 import SearchRequestV2
    from hedge_shared.store_v1 import validate_offline_store_scope

    validate_offline_store_scope(None, None)
    validate_offline_store_scope("Store", "hedge_store_offline_" + "a" * 32)
    with pytest.raises(ValidationError):
        SearchRequestV2.model_validate({
            "query": "energy", "store_id": "Store",
            "collection_name": "hedge_store_offline_" + "a" * 32,
        })

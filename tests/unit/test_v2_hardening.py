"""Contract, semantic-profile, and fail-closed production tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hedge_shared.models_v2 import (
    SUPPORTED_LOCALES,
    AppMetadataV2,
    RecommendationEventRequest,
    SemanticAnnotation,
)
from hedge_shared.production import validate_production_environment
from hedge_shared.saref import app_to_jsonld, is_allowed_saref_uri, validate_annotation
from pydantic import ValidationError

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def app() -> AppMetadataV2:
    records = json.loads(
        (ROOT / "services/mock-api/app/data/apps-v2.json").read_text(encoding="utf-8")
    )
    return AppMetadataV2.model_validate(records[0])


def test_catalogue_fixture_has_all_supported_locales(app: AppMetadataV2) -> None:
    assert set(app.localized_keywords) == set(SUPPORTED_LOCALES)
    assert all(app.title.for_locale(locale) for locale in SUPPORTED_LOCALES)


def test_checksum_is_stable_and_changes_with_content(app: AppMetadataV2) -> None:
    payload = app.model_dump(exclude={"checksum"})
    assert app.checksum == AppMetadataV2.model_validate(payload).checksum
    changed = app.model_copy(update={"description": f"{app.description} changed"})
    assert changed.checksum != app.checksum


def test_index_text_uses_locale_and_semantic_evidence(app: AppMetadataV2) -> None:
    text = app.to_index_text("de")
    assert app.summary.de in text
    assert "Function" in text


def test_v2_contract_rejects_unknown_fields(app: AppMetadataV2) -> None:
    payload = app.model_dump(mode="json", exclude={"checksum"})
    payload["legacy_score"] = 0.99
    with pytest.raises(ValidationError, match="Extra inputs"):
        AppMetadataV2.model_validate(payload)


def test_catalogue_strings_are_normalized_and_deduplicated(app: AppMetadataV2) -> None:
    payload = app.model_dump(mode="json", exclude={"checksum"})
    payload["tags"] = [" Energy ", "energy", "metering"]
    normalized = AppMetadataV2.model_validate(payload)
    assert normalized.tags == ["Energy", "metering"]


def test_inferred_annotation_requires_confidence() -> None:
    with pytest.raises(ValidationError, match="require confidence"):
        SemanticAnnotation(
            term_uri="https://saref.etsi.org/core/Device",
            label="Device",
            ontology_uri="https://saref.etsi.org/core/",
            ontology_version="4.1.1",
            relation="device-kind",
            provenance="inferred",
        )


def test_reviewed_annotation_requires_date() -> None:
    with pytest.raises(ValidationError, match="require reviewed_at"):
        SemanticAnnotation(
            term_uri="https://saref.etsi.org/core/Device",
            label="Device",
            ontology_uri="https://saref.etsi.org/core/",
            ontology_version="4.1.1",
            relation="device-kind",
            provenance="curated",
            review_status="approved",
        )


def test_uri_registry_rejects_lookalike_host() -> None:
    assert is_allowed_saref_uri("https://saref.etsi.org/core/Device")
    assert not is_allowed_saref_uri("https://saref.etsi.org.example/core/Device")


def test_domain_annotation_must_use_extension_root() -> None:
    annotation = SemanticAnnotation(
        term_uri="https://saref.etsi.org/core/Device",
        label="Device",
        ontology_uri="https://saref.etsi.org/core/",
        ontology_version="4.1.1",
        relation="domain",
        provenance="curated",
    )
    assert "domain annotations" in " ".join(validate_annotation(annotation))


def test_jsonld_has_stable_identity_and_uri_context(app: AppMetadataV2) -> None:
    document = app_to_jsonld(app)
    assert document["@id"].endswith(app.id)
    assert document["@type"] == "SoftwareApplication"
    assert document["@context"]["termUri"]["@type"] == "@id"


def test_app_open_event_requires_app_reference() -> None:
    with pytest.raises(ValidationError, match="app_id is required"):
        RecommendationEventRequest(
            impression_id="imp-test",
            idempotency_key="evt-test",
            event_type="app_opened",
        )


def test_response_event_rejects_app_reference() -> None:
    with pytest.raises(ValidationError, match="only allowed"):
        RecommendationEventRequest(
            impression_id="imp-test",
            idempotency_key="evt-test",
            event_type="recommendation_accepted",
            app_id="app-001",
        )


def test_valid_event_defaults_to_utc_timestamp() -> None:
    event = RecommendationEventRequest(
        impression_id="imp-test",
        idempotency_key="evt-test",
        event_type="app_opened",
        app_id="app-001",
    )
    assert event.occurred_at.tzinfo is not None
    assert event.occurred_at <= datetime.now(UTC)


def test_development_configuration_remains_convenient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    validate_production_environment()


def test_production_rejects_permissive_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("POSTGRES_PASSWORD", "hedge-dev-only")
    with pytest.raises(RuntimeError, match="unsafe production configuration"):
        validate_production_environment()


def test_production_accepts_explicit_safe_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "APP_ENV": "production",
        "CORS_ALLOWED_ORIGINS": "https://store.example",
        "ENABLE_RBAC": "true",
        "OAUTH_ENABLED": "true",
        "RATE_LIMIT_REQUIRED": "true",
        "ENABLE_HSTS": "true",
        "OAUTH_ISSUER": "https://identity.example/realms/hedge",
        "OAUTH_JWKS_URL": "https://identity.example/keys",
        "POSTGRES_PASSWORD": "a-long-secret-from-a-file",
        "OAUTH_SHARED_SECRET": "",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    validate_production_environment()

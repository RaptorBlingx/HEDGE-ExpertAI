"""Observable source-field dialogue, with the real Store quotation renderer."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from hedge_shared.models_v2 import ChatRequestV2

from scripts.store_v1_playground import load_service

policy_module = load_service("source_fields_chat", "chat-intent")("store_dialogue")
normalize = load_service("source_fields_ingest", "metadata-ingest")("client").normalize_store_v1_app
render = load_service("source_fields_expert", "expert-recommend")("recommender")._recommendation_narrative
RAW = json.loads((Path(__file__).parents[1] / "fixtures/store-v1/browser-metadata-apps.json").read_text())


@pytest.fixture
def source_dialogue():
    apps = [normalize(r).recommendation_projection() for r in RAW if r["visible"]]
    search = AsyncMock(return_value={"apps": [], "message": "No matches"})
    generator = Mock(side_effect=lambda q, a, loc, intent, fallback: {
        "message": fallback, "generation": {"source": "deterministic"},
    })
    policy = policy_module.StoreDialogue(search, lambda ids: [a for a in apps if ids is None or a["id"] in ids], render, generator)

    def ask(message, filters=None):
        return asyncio.run(policy.respond(ChatRequestV2(message=message, filters=filters or {}), "search",
                                          {"focused_ids": [apps[0]["id"]], "last_results": [{"app": a} for a in apps]}))

    return apps, ask, search, generator


@pytest.mark.parametrize(("field", "path", "value"), [
    ("README", "readme", "production compatibility has not been validated"),
    ("embedded metadata", "dataspaceAppDescription.properties.featureList", "Heat network diagnostics"),
    ("connector fields", "builtForConnector", "DemoConnector"),
    ("connector version", "connectorVersion", "1.2"),
    ("billing fields", "billable", "false"),
    ("price", "price", "0.0"),
    ("versions", "appVersionList", "0.3-demo"),
    ("type", "type", "APP"),
])
def test_explicit_source_read_uses_complete_cited_evidence(source_dialogue, field, path, value):
    apps, ask, search, generator = source_dialogue
    response = ask(f"Show {field} for Demo Telemetry Bridge")
    assert response["intent"] == "source_fields"
    assert response["apps"][0]["app"] == apps[0]
    assert response["context"]["focused_ids"] == [apps[0]["id"]]
    assert path in response["message"] and value in response["message"]
    assert "do not establish suitability or compatibility" in response["message"]
    assert "unsafeSource" not in response["message"]
    assert "excluded-demo-secret" not in response["message"]
    search.assert_not_awaited()
    generator.assert_not_called()


def test_billing_and_versions_do_not_invent_business_semantics(source_dialogue):
    _, ask, _, _ = source_dialogue
    assert "Currency, billing period, taxes and licence terms are unspecified" in ask("Show billing fields for it")["message"]
    assert "does not establish that an App is free" in ask("Show price for it")["message"]
    assert "no current or latest version is inferred" in ask("Show versions for it")["message"]


@pytest.mark.parametrize(("prompt", "status"), [
    ("Show README for Demo Sparse Catalogue", "missing"),
    ("Show embedded metadata for Demo Sparse Catalogue", "malformed"),
    ("Show README for Demo Long Documentation", "too_large"),
])
def test_source_extraction_status_is_not_claimed_as_capability_absence(source_dialogue, prompt, status):
    response = source_dialogue[1](prompt)
    assert f"evidence is {status}" in response["message"]
    assert "does not establish absence" in response["message"]
    assert len(response["apps"]) == 1


@pytest.mark.parametrize("size", [1200, 1201])
def test_source_read_does_not_cut_qualification(source_dialogue, size):
    apps, ask, _, _ = source_dialogue
    value = "x" * (size - len(" MQTT is not supported.")) + " MQTT is not supported."
    apps[0]["source_evidence"]["readme"] = value
    response = ask("Show README for it")
    if size == 1200:
        assert value in response["message"]
    else:
        assert value[:100] not in response["message"]
        assert "complete quotation omitted" in response["message"]


def test_source_read_respects_publication_and_does_not_accept_new_constraints(source_dialogue):
    _, ask, _, _ = source_dialogue
    assert not ask("Show README for Demo Unpublished App")["apps"]
    for query in ("Show price for only free apps", "Show README for Demo Telemetry Bridge and confirm MQTT support"):
        assert not ask(query)["apps"]
    assert not ask("Show README for it", {"capabilities": ["MQTT"]})["apps"]


def test_source_targets_are_exact_and_native_ids_remain_case_sensitive(source_dialogue):
    apps, ask, _, _ = source_dialogue
    assert ask("Show README for demo-telemetry")["apps"][0]["app"]["id"] == apps[0]["id"]
    assert not ask("Show README for DEMO-TELEMETRY")["apps"]
    # A field name cannot accidentally select an App with that name.
    apps[1]["name"] = "README"
    assert ask("Show README")["apps"][0]["app"]["id"] == apps[0]["id"]
    # Duplicate titles must not merge native App identities.
    apps[1]["name"] = apps[0]["name"]
    assert not ask("Show README for Demo Telemetry Bridge")["apps"]
    assert len(ask("Show README for demo-telemetry")["apps"]) == 1

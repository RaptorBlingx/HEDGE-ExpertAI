"""Real PostgreSQL/Valkey dialogue and existing offline recommendation wiring."""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse

import pytest
from hedge_shared import storage
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_v1_playground import load_service

from .test_store_v1_persistence import database as database
from .test_store_v1_recommendations import RAW, STORE, client_module, recommender
from .test_store_v1_recommendations import offline as offline

chat = load_service("integration_store_chat", "chat-intent")("routes")
policy_module = __import__(chat.__package__ + ".store_dialogue", fromlist=["StoreDialogue"])


@pytest.fixture
def conversation(offline, monkeypatch):
    if urlparse(os.getenv("VALKEY_SESSION_URL", "")).hostname != "sessions":
        pytest.skip("requires explicitly isolated sessions Valkey")
    monkeypatch.setenv("RASA_ENABLED", "false")
    identities = [client_module.normalize_store_v1_app(r).id for r in RAW if r["fkAppStoreId"] == STORE]

    def resolve(ids):
        ids = identities if ids is None else ids
        rows = storage.get_catalogue_apps(ids, store_id=STORE)
        return [StoreAppMetadata.model_validate(rows[i]["payload"]).recommendation_projection()
                for i in ids if i in rows]

    async def search(**kwargs):
        return recommender.recommend_v2(**kwargs, limit=5)

    policy = policy_module.StoreDialogue(search, resolve, recommender._recommendation_narrative)
    sessions = set()
    session = None

    def ask(message):
        nonlocal session
        result = asyncio.run(chat.run_chat_v2(ChatRequestV2(message=message, session_id=session), store_dialogue=policy))
        session = result["session_id"]
        sessions.add(session)
        return result

    yield ask
    for identity in sessions:
        chat.delete_session(identity)


def test_real_dialogue_details_comparison_smalltalk_and_unsupported_context(conversation):
    initial = conversation("readings")
    assert len(initial["apps"]) == 2
    ids = [a["app"]["id"] for a in initial["apps"]]
    detail = conversation("Tell me more about the second app")
    assert detail["apps"][0]["app"]["id"] == ids[1]
    conversation("hello")
    comparison = conversation("Compare the first two apps")
    assert [a["app"]["id"] for a in comparison["apps"]] == ids
    assert "Source-field comparison only" in comparison["message"]
    assert "cannot confirm" in conversation("Only free apps instead")["message"]
    assert conversation("Tell me about the first app")["apps"][0]["app"]["id"] == ids[0]
    assert conversation("reset")["apps"] == []
    assert conversation("Describe the first app")["apps"] == []


def test_followups_rehydrate_current_metadata_and_reject_withdrawal(conversation):
    initial = conversation("energy")
    app = StoreAppMetadata.model_validate(storage.get_catalogue_apps([initial["apps"][0]["app"]["id"]], store_id=STORE)[initial["apps"][0]["app"]["id"]]["payload"])
    changed = app.model_copy(update={"description": "Current authoritative description"})
    storage.upsert_catalogue_app(storage.create_ingestion_run("dialogue-update"), changed)
    result = conversation("Tell me about the first app")
    assert "Current authoritative description" in result["message"]
    withdrawn = changed.model_copy(update={"visible": False})
    storage.upsert_catalogue_app(storage.create_ingestion_run("dialogue-withdrawal"), withdrawn)
    assert conversation("Tell me about the first app")["apps"] == []
    assert conversation("Compare both")["apps"] == []


def test_new_empty_topic_discards_old_references(conversation):
    assert conversation("energy")["apps"]
    assert conversation("zzzzunmatchedtopic")["apps"] == []
    assert conversation("Tell me about the first app")["apps"] == []


def test_metadata_answers_use_current_persisted_evidence_and_keep_withdrawal(conversation):
    initial = conversation("energy")
    identity = initial["apps"][0]["app"]["id"]
    app = StoreAppMetadata.model_validate(storage.get_catalogue_apps([identity], store_id=STORE)[identity]["payload"])
    changed = app.model_copy(update={
        "readme": "<p>thermaldiagnostic collection is available only in the simulator.</p><script>unsafeSource</script>",
        "built_for_connector": "ExampleConnector", "connector_version": "1.2",
        "billable": False, "price": 0,
        "dataspace_app_description": '{"properties":{"description":"districtdiagnostic inspection"}}',
    })
    storage.upsert_catalogue_app(storage.create_ingestion_run("metadata-dialogue"), changed)
    # Match evidence absent from title/description through real PostgreSQL lexical search.
    found = conversation("thermaldiagnostic")
    assert found["apps"] == []  # Simulation-only evidence is not a recommendation.
    candidate = next(r for r in found["candidates"] if r["app"]["id"] == identity)
    assert "lexical" in candidate["evidence_fields"]
    conversation(f"Tell me about {app.app_id}")  # Explicit candidate inspection binds focus.
    readme = conversation("Show README for it")
    assert "readme:" in readme["message"] and "only in the simulator" in readme["message"]
    assert "unsafeSource" not in readme["message"]
    assert readme["apps"][0]["app"]["store_id"] == STORE
    assert readme["apps"][0]["app"]["app_id"] == app.app_id
    embedded = conversation("Show embedded metadata for it")
    assert "dataspaceAppDescription.properties.description" in embedded["message"]
    assert "districtdiagnostic" in embedded["message"]
    billing = conversation("Show billing fields for it")
    assert 'billable: "false"' in billing["message"]
    assert 'price: "0"' in billing["message"] or 'price: "0.0"' in billing["message"]
    assert "Currency, billing period, taxes and licence terms are unspecified" in billing["message"]
    assert 'connectorVersion: "1.2"' in conversation("Show connector fields for it")["message"]
    # A changed source is rehydrated; neither history nor vector payload supplies facts.
    storage.upsert_catalogue_app(storage.create_ingestion_run("metadata-change"), changed.model_copy(update={"readme": "x" * 16001}))
    assert "evidence is too_large" in conversation("Show README for it")["message"]
    storage.upsert_catalogue_app(storage.create_ingestion_run("metadata-withdrawal"), changed.model_copy(update={"visible": False}))
    assert conversation("Show README for it")["apps"] == []


def test_private_contextual_http_sse_fallback_and_withdrawal(offline, monkeypatch):
    """Real persistence/search/sessions behind the same private browser adapter."""
    import json
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from scripts.store_v1_browser import create_app
    from scripts.store_v1_playground import Playground

    answers = __import__(recommender.__package__ + ".store_answers", fromlist=["respond"])
    identities = [client_module.normalize_store_v1_app(r).id for r in RAW if r["fkAppStoreId"] == STORE]

    def resolve(ids):
        ids = identities if ids is None else ids
        rows = storage.get_catalogue_apps(ids, store_id=STORE)
        return [StoreAppMetadata.model_validate(rows[i]["payload"]).recommendation_projection() for i in ids if i in rows]

    async def search(**kwargs):
        return recommender.recommend_v2(**kwargs, limit=5)

    def failed_model():
        raise TimeoutError("private model output")

    monkeypatch.setattr(answers, "OllamaClient", failed_model)
    # Reproduce the deployed Rasa misclassification without allowing it to own
    # application dialogue or prevent explicit entity/reference resolution.
    monkeypatch.setattr(chat, "classify", lambda msg: SimpleNamespace(intent="help", source="rasa", confidence=1.0))
    policy = policy_module.StoreDialogue(search, resolve, answers.render, answers.respond, catalogue_references=True)
    playground = Playground(chat, recommender, __import__("hedge_shared.models_v2", fromlist=["ChatRequestV2"]), [], policy)
    sessions = set()
    try:
        with TestClient(create_app(playground), base_url="http://127.0.0.1:8098") as browser:
            normal = browser.post("/api/v2/chat", json={"message": "Tell me about the first app"}).json()
            session = normal["session_id"]
            sessions.add(session)
            assert len(normal["apps"]) == 1 and normal["impression_id"]
            assert normal["generation"]["reason"] == "no_source_fields"  # first fixture is deliberately empty
            assert "private model output" not in normal["message"]
            same = browser.post("/api/v2/chat/stream", json={"message": "Tell me about the first app", "session_id": session})
            events = [json.loads(line[6:]) for line in same.text.splitlines() if line.startswith("data: ")]
            assert next(e["apps"] for e in events if e["type"] == "recommendations") == normal["apps"]
            assert next(e["content"] for e in events if e["type"] == "explanation_delta") == normal["message"].replace("References use the observed catalogue order shown on this page.\n", "")
            compared = browser.post("/api/v2/chat", json={"message": "Compare the first two apps", "session_id": session}).json()
            assert len(compared["apps"]) == 2
            assert "no superiority or suitability" in compared["message"]
            app = next(a for a in resolve(None) if a.get("name") and a.get("description"))
            named = browser.post("/api/v2/chat", json={"message": "Tell me about " + app["name"]}).json()
            sessions.add(named["session_id"])
            assert named["generation"]["reason"] == "model_unavailable_or_timeout"
            assert named["apps"][0]["app"]["id"] == app["id"]
            follow = browser.post("/api/v2/chat", json={"message": "Describe it", "session_id": named["session_id"]}).json()
            assert follow["apps"] == named["apps"]
            rows = storage.get_catalogue_apps([app["id"]], store_id=STORE)
            current = StoreAppMetadata.model_validate(rows[app["id"]]["payload"])
            storage.upsert_catalogue_app(storage.create_ingestion_run("context-withdraw"), current.model_copy(update={"visible": False}))
            withdrawn = browser.post("/api/v2/chat", json={"message": "Describe it", "session_id": named["session_id"]}).json()
            assert withdrawn["apps"] == [] and withdrawn["impression_id"] is None
    finally:
        for session in sessions:
            chat.delete_session(session)

"""Real PostgreSQL/Valkey dialogue through the Store assistant and the offline recommendation path.

Act classification is a fixed table here: these tests are about persistence,
sessions, current metadata and withdrawal, not about language understanding.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
from urllib.parse import urlparse

import pytest
from hedge_shared import storage
from hedge_shared.models_v2 import ChatRequestV2
from hedge_shared.store_knowledge import project
from hedge_shared.store_v1 import StoreAppMetadata

from scripts.store_assistant_local import local_assistant
from scripts.store_v1_playground import load_service

from .test_store_v1_persistence import database as database
from .test_store_v1_recommendations import RAW, STORE, client_module, recommender
from .test_store_v1_recommendations import offline as offline

chat = load_service("integration_store_chat", "chat-intent")("routes")
ACTS = {"readings": "find", "energy": "find", "zzzzunmatchedtopic": "find", "thermaldiagnostic": "find",
        "hello": "greeting", "reset": "reset", "only free apps instead": "find", "compare both": "compare",
        "compare the first two apps": "compare", "how much does it cost?": "price",
        "which connector does it use?": "details"}


def policy(resolve):
    labels = [n for n, a in importlib.import_module(chat.__package__ + ".understanding").acts().items()
              for _ in a["examples"]]

    def semantic(text, examples):
        act = ACTS.get(text.casefold(), "describe")
        return [1.0 if label == act else 0.5 for label in labels]

    async def search(**kwargs):
        return recommender.recommend_v2(**kwargs, limit=5)

    return local_assistant(lambda m: importlib.import_module(f"{chat.__package__}.{m}"),
                           lambda m: importlib.import_module(f"{recommender.__package__}.{m}"),
                           recommend=search, resolve=resolve, semantic=semantic, rasa_url="")


def resolver():
    identities = [client_module.normalize_store_v1_app(r).id for r in RAW if r["fkAppStoreId"] == STORE]

    def resolve(ids):
        # The same current projection Discovery's catalogue route serves.
        ids = identities if ids is None else ids
        rows = storage.get_catalogue_apps(ids, store_id=STORE)
        return [project(rows[i]) for i in ids if i in rows]
    return resolve


@pytest.fixture
def conversation(offline, monkeypatch):
    if urlparse(os.getenv("VALKEY_SESSION_URL", "")).hostname != "sessions":
        pytest.skip("requires explicitly isolated sessions Valkey")
    monkeypatch.setenv("RASA_ENABLED", "false")
    assistant = policy(resolver())
    sessions = set()
    session = None

    def ask(message):
        nonlocal session
        result = asyncio.run(chat.run_chat_v2(ChatRequestV2(message=message, session_id=session), assistant=assistant))
        session = result["session_id"]
        sessions.add(session)
        return result

    yield ask
    for identity in sessions:
        chat.delete_session(identity)


def test_real_dialogue_details_comparison_smalltalk_and_unverified_conditions(conversation):
    initial = conversation("readings")
    ids = [a["app"]["id"] for a in initial["apps"]]
    assert len(ids) == 2
    assert conversation("Tell me more about the second app")["apps"][0]["app"]["id"] == ids[1]
    conversation("hello")
    assert [a["app"]["id"] for a in conversation("Compare the first two apps")["apps"]] == ids
    unverified = conversation("Only free apps instead")
    assert unverified["apps"] == [] and "doesn’t establish which Apps meet your pricing" in unverified["message"]
    assert conversation("Tell me about the first app")["apps"][0]["app"]["id"] == ids[0]
    assert conversation("reset")["apps"] == []
    assert conversation("Describe the first app")["apps"] == []


def test_followups_rehydrate_current_metadata_and_reject_withdrawal(conversation):
    initial = conversation("energy")
    identity = initial["apps"][0]["app"]["id"]
    app = StoreAppMetadata.model_validate(storage.get_catalogue_apps([identity], store_id=STORE)[identity]["payload"])
    changed = app.model_copy(update={"description": "Current authoritative description", "readme": None})
    storage.upsert_catalogue_app(storage.create_ingestion_run("dialogue-update"), changed)
    assert "Current authoritative description" in conversation("Tell me about the first app")["message"]
    storage.upsert_catalogue_app(storage.create_ingestion_run("dialogue-withdrawal"), changed.model_copy(update={"visible": False}))
    assert conversation("Tell me about the first app")["apps"] == []
    # Whatever "both" can still mean, the withdrawn App is never shown.
    assert identity not in [a["app"]["id"] for a in conversation("Compare both")["apps"]]


def test_new_empty_topic_discards_old_references(conversation):
    assert conversation("energy")["apps"]
    assert conversation("zzzzunmatchedtopic")["apps"] == []
    assert conversation("Tell me about the first app")["apps"] == []


def test_field_answers_use_current_persisted_evidence_and_keep_withdrawal(conversation):
    initial = conversation("energy")
    identity = initial["apps"][0]["app"]["id"]
    app = StoreAppMetadata.model_validate(storage.get_catalogue_apps([identity], store_id=STORE)[identity]["payload"])
    changed = app.model_copy(update={
        "readme": "<p>thermaldiagnostic collection is available only in the simulator.</p><script>unsafeSource</script>",
        "built_for_connector": "ExampleConnector", "connector_version": "1.2", "billable": False, "price": 0})
    storage.upsert_catalogue_app(storage.create_ingestion_run("metadata-dialogue"), changed)
    # Match evidence absent from title/description through real PostgreSQL lexical search.
    found = conversation("thermaldiagnostic")
    assert found["apps"] == []  # Simulation-only evidence is not a recommendation.
    assert "lexical" in next(r for r in found["candidates"] if r["app"]["id"] == identity)["evidence_fields"]
    described = conversation(f"Tell me about {app.app_id}")  # an exact native ID binds the subject
    assert described["apps"][0]["app"]["app_id"] == app.app_id and "unsafeSource" not in described["message"]
    assert "doesn’t establish free use" in conversation("How much does it cost?")["message"]
    assert "Connector version: 1.2" in conversation("Which connector does it use?")["message"]
    storage.upsert_catalogue_app(storage.create_ingestion_run("metadata-withdrawal"), changed.model_copy(update={"visible": False}))
    assert conversation("Tell me about it")["apps"] == []


def test_private_http_and_sse_share_identity_and_withdrawal(offline, monkeypatch):
    """Real persistence/search/sessions behind the private browser adapter."""
    from fastapi.testclient import TestClient

    from scripts.store_v1_browser import create_app
    from scripts.store_v1_playground import Playground

    monkeypatch.setenv("RASA_ENABLED", "false")
    resolve = resolver()
    playground = Playground(chat, recommender, __import__("hedge_shared.models_v2", fromlist=["ChatRequestV2"]), [],
                            policy(resolve))
    sessions = set()
    try:
        with TestClient(create_app(playground), base_url="http://127.0.0.1:8098") as browser:
            listed = browser.post("/api/v2/chat", json={"message": "energy"}).json()
            session = listed["session_id"]
            sessions.add(session)
            normal = browser.post("/api/v2/chat", json={"message": "Tell me about the first app", "session_id": session}).json()
            assert len(normal["apps"]) == 1 and normal["impression_id"]
            same = browser.post("/api/v2/chat/stream", json={"message": "Tell me about the first app", "session_id": session})
            events = [json.loads(line[6:]) for line in same.text.splitlines() if line.startswith("data: ")]
            assert next(e["apps"] for e in events if e["type"] == "recommendations") == normal["apps"]
            assert "".join(e["content"] for e in events if e["type"] == "explanation_delta") == normal["message"]
            app = next(a for a in resolve(None) if a.get("name") and a.get("description"))
            named = browser.post("/api/v2/chat", json={"message": "Tell me about " + app["name"]}).json()
            sessions.add(named["session_id"])
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

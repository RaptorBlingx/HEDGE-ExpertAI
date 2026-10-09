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
    initial = conversation("energy")
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

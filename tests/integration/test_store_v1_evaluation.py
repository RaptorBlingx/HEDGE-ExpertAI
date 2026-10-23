"""Private snapshot input through the real disposable Store pipeline, no remote calls."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import psycopg
import pytest
from hedge_shared import storage
from hedge_shared.store_v1 import StoreAppMetadata
from psycopg import sql

from scripts.store_v1_playground import offline_playground


@pytest.fixture
def isolated_input(tmp_path, monkeypatch):
    dsn = os.getenv("HEDGE_TEST_DATABASE_URL", "")
    url = urlsplit(dsn)
    if url.hostname != "database" or url.path != "/hedge_phase1_test":
        pytest.skip("requires the disposable playground database")
    if os.getenv("VALKEY_SESSION_URL") != "redis://sessions:6379/0":
        pytest.skip("requires disposable playground sessions")
    schema = "evaluation_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = urlunsplit(url._replace(query=urlencode({"options": "-csearch_path=" + schema})))
    monkeypatch.setenv("DATABASE_URL", scoped)
    monkeypatch.setenv("RASA_ENABLED", "false")
    monkeypatch.setenv("STORE_PLAYGROUND_E5", "false")
    monkeypatch.setenv("STORE_PLAYGROUND_ID", "Different-Evaluation-Store")
    monkeypatch.setenv("STORE_PLAYGROUND_SOURCE", "private-json-import")
    raw = json.loads(Path("tests/fixtures/store-v1/manual-apps.json").read_text())
    for record in raw:
        record["fkAppStoreId"] = "Different-Evaluation-Store"
    raw.append(dict(raw[0], appId="unpublished-sentinel", name="Unpublished sentinel", visible=False))
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(raw))
    monkeypatch.setenv("STORE_PLAYGROUND_INPUT", str(path))
    try:
        yield
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_import_reuses_scoped_dialogue_and_never_recommends_unpublished_apps(isolated_input):
    with offline_playground() as evaluation:
        try:
            assert evaluation.source == "private-json-import"
            assert len(evaluation.records) == 2
            assert all(r["store_id"] == "Different-Evaluation-Store" for r in evaluation.records)
            result = evaluation.ask("Show me EdgeConnect and Semantic Treehouse", "chat", {})["result"]
            ids = [r["app"]["id"] for r in result["apps"]]
            assert len(ids) == 2
            detail = evaluation.ask("Tell me about the second app", "chat", {})["result"]
            assert detail["apps"][0]["app"]["id"] == ids[1]
            comparison = evaluation.ask("Compare both", "chat", {})["result"]
            assert [r["app"]["id"] for r in comparison["apps"]] == ids
            assert "Source-field comparison only" in comparison["message"]
            assert evaluation.ask("Unpublished sentinel", "search", {})["result"]["apps"] == []
            with storage.connection() as conn:
                run = conn.execute("SELECT status, deleted_count FROM ingestion_runs").fetchone()
                assert run == {"status": "partial", "deleted_count": 0}
                assert conn.execute("SELECT count(*) AS n FROM indexing_outbox").fetchone()["n"] == 0
                assert conn.execute("SELECT count(*) AS n FROM catalog_apps").fetchone()["n"] == 3
        finally:
            if evaluation.session_id:
                evaluation.chat.delete_session(evaluation.session_id)


def test_browse_rehydrates_publication_metadata_and_reappearance(isolated_input):
    with offline_playground() as evaluation:
        try:
            initial = evaluation.ask("Show me all available applications", "chat", {})["result"]
            assert initial["intent"] == "browse"
            assert len(initial["apps"]) == 2
            assert "snapshot may be incomplete" in initial["message"]
            app_id = initial["apps"][0]["app"]["id"]
            row = storage.get_catalogue_apps([app_id], store_id="Different-Evaluation-Store")[app_id]
            current = StoreAppMetadata.model_validate(row["payload"])
            run_id = storage.create_ingestion_run("isolated-evaluation")
            changed = current.model_copy(update={"description": "Current authoritative browse description"})
            storage.upsert_catalogue_app(run_id, changed)
            result = evaluation.ask("List Apps", "chat", {})["result"]
            assert "Current authoritative browse description" in result["message"]
            storage.upsert_catalogue_app(run_id, changed.model_copy(update={"visible": False}))
            storage.upsert_catalogue_app(run_id, StoreAppMetadata(
                store_id="Another-Store", app_id=current.app_id, name="Wrong Store", active=True, visible=True))
            published = StoreAppMetadata(store_id="Different-Evaluation-Store", app_id="unpublished-sentinel",
                                         name="Reappeared source App", active=True, visible=True)
            storage.upsert_catalogue_app(run_id, published)
            result = evaluation.ask("What applications are available?", "chat", {})["result"]
            assert len(result["apps"]) == 2
            assert app_id not in [r["app"]["id"] for r in result["apps"]]
            assert published.id in [r["app"]["id"] for r in result["apps"]]
            assert all(r["app"]["store_id"] == "Different-Evaluation-Store" for r in result["apps"])
            native = result["apps"][1]["app"]["app_id"]
            assert evaluation.ask("Tell me about the second app", "chat", {})["result"]["apps"][0]["app"]["app_id"] == native
            storage.upsert_catalogue_app(run_id, published.model_copy(update={"active": False}))
            storage.upsert_catalogue_app(run_id, current.model_copy(update={"active": False}))
            remaining = [r for r in evaluation.records if r["id"] != current.id][0]
            row = storage.get_catalogue_apps([remaining["id"]], store_id="Different-Evaluation-Store")[remaining["id"]]
            storage.upsert_catalogue_app(run_id, StoreAppMetadata.model_validate(row["payload"]).model_copy(update={"visible": False}))
            result = evaluation.ask("Browse applications", "chat", {})["result"]
            assert result["apps"] == []
            assert "Showing 0" in result["message"]
            assert evaluation.ask("Tell me about the first app", "chat", {})["result"]["apps"] == []
        finally:
            if evaluation.session_id:
                evaluation.chat.delete_session(evaluation.session_id)


def test_grounded_reply_is_saved_in_history_and_rechecks_late_publication(isolated_input, monkeypatch):
    from types import SimpleNamespace

    from scripts.store_v1_playground import load_service
    monkeypatch.setenv('STORE_PLAYGROUND_OLLAMA','true')
    recommend=load_service('manual_store_expert','expert-recommend')('recommender')
    withdraw=False

    def generate(messages, schema):
        sources=json.loads(messages[1]['content'])['untrusted_source_fields']
        if withdraw:
            with storage.connection() as conn:
                conn.execute("UPDATE catalog_apps SET active=false")  # Only this test's guarded schema.
        return json.dumps({'apps':[{'rank':r['rank'],'evidence':[
            {'field':'description','quote':r['description'][0]}]} for r in sources]})

    monkeypatch.setattr(recommend,'OllamaClient',lambda:SimpleNamespace(model='offline-validator-fixture',chat_structured=generate))
    with offline_playground() as evaluation:
        try:
            result=evaluation.ask('List applications','chat',{})['result']
            assert result['generation']['source']=='ollama'
            assert 'Validated Ollama source excerpts' in result['message']
            assert evaluation.chat.get_session(evaluation.session_id)['messages'][-1]['content']==result['message']
            withdraw=True
            result=evaluation.ask('Compare both','chat',{})['result']
            assert result['apps']==[]
            assert result['generation']['reason']=='catalogue_changed'
            assert 'snapshot changed' in result['message']
        finally:
            if evaluation.session_id:
                evaluation.chat.delete_session(evaluation.session_id)

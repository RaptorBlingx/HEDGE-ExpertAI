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

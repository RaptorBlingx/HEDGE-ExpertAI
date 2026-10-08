"""Repository-level tests for durable catalogue, outbox, and KPI behavior."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hedge_shared import storage
from hedge_shared.models_v2 import (
    AppMetadataV2,
    RecommendationEventRequest,
    SearchFilters,
)
from hedge_shared.store_v1 import StoreAppMetadata

ROOT = Path(__file__).parents[2]


class FakeCursor:
    def __init__(
        self,
        *,
        one: list[Any] | None = None,
        many: list[Any] | None = None,
        rowcounts: list[int] | None = None,
    ) -> None:
        self.one = list(one or [])
        self.many = list(many or [])
        self.rowcounts = list(rowcounts or [])
        self.rowcount = 0
        self.executed: list[tuple[str, Any]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((" ".join(sql.split()), params))
        if self.rowcounts:
            self.rowcount = self.rowcounts.pop(0)

    def fetchone(self) -> Any:
        return self.one.pop(0)

    def fetchall(self) -> Any:
        return self.many.pop(0)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.fake_cursor = cursor

    def cursor(self) -> FakeCursor:
        return self.fake_cursor


def install_connection(monkeypatch: pytest.MonkeyPatch, cursor: FakeCursor) -> None:
    @contextmanager
    def fake_connection():
        yield FakeConnection(cursor)

    monkeypatch.setattr(storage, "connection", fake_connection)


@pytest.fixture(scope="module")
def app() -> AppMetadataV2:
    records = json.loads(
        (ROOT / "services/mock-api/app/data/apps-v2.json").read_text(encoding="utf-8")
    )
    return AppMetadataV2.model_validate(records[0])


def test_database_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/hedge")
    assert storage.database_url() == "postgresql://example.invalid/hedge"


def test_ping_database_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(one=[{"?column?": 1}])
    install_connection(monkeypatch, cursor)
    assert storage.ping_database()

    @contextmanager
    def unavailable():
        raise RuntimeError("database down")
        yield

    monkeypatch.setattr(storage, "connection", unavailable)
    assert not storage.ping_database()


def test_ingestion_run_lifecycle_and_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(
        one=[
            {"id": "newest", "status": "completed"},
            {"id": "specific", "status": "partial"},
        ]
    )
    install_connection(monkeypatch, cursor)
    run_id = storage.create_ingestion_run("fixture-v2")
    assert len(run_id) == 36
    storage.complete_ingestion_run(
        run_id,
        status="completed",
        fetched=2,
        created=1,
        updated=0,
        unchanged=1,
        deleted=0,
        quarantined=0,
    )
    assert storage.latest_ingestion_run()["id"] == "newest"
    assert storage.get_ingestion_run(run_id)["id"] == "specific"
    assert any("INSERT INTO ingestion_runs" in sql for sql, _ in cursor.executed)
    assert any("completed_at = now()" in sql for sql, _ in cursor.executed)


def test_quarantine_storage_and_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(
        one=[{"total": 1}],
        many=[[{"source_key": "bad-1", "validation_errors": ["missing id"]}]],
    )
    install_connection(monkeypatch, cursor)
    storage.quarantine_item(
        "run-id",
        source_key="bad-1",
        payload={"title": "invalid"},
        errors=["missing id"],
    )
    total, rows = storage.list_quarantined_items(run_id="run-id", limit=10, offset=5)
    assert total == 1
    assert rows[0]["source_key"] == "bad-1"
    assert cursor.executed[-1][1] == ["run-id", 10, 5]


def test_upsert_catalogue_created_updated_and_unchanged(
    app: AppMetadataV2,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = FakeCursor(one=[{"source": "fixture"}, None])
    install_connection(monkeypatch, created)
    assert storage.upsert_catalogue_app("run-1", app) == "created"
    assert any("INSERT INTO indexing_outbox" in sql for sql, _ in created.executed)

    updated = FakeCursor(
        one=[
            {"source": "fixture"},
            {
                "checksum": "different",
                "revision": 4,
                "schema_version": "2.0",
                "active": True,
                "last_seen_run_id": "owner",
            },
            {"source": "fixture"},
        ]
    )
    install_connection(monkeypatch, updated)
    assert storage.upsert_catalogue_app("run-2", app) == "updated"
    catalogue_params = next(
        params for sql, params in updated.executed if "INSERT INTO catalog_apps" in sql
    )
    assert catalogue_params[2] == 5

    unchanged = FakeCursor(
        one=[
            {"source": "fixture"},
            {
                "checksum": app.checksum,
                "revision": 5,
                "schema_version": "2.0",
                "active": True,
                "last_seen_run_id": "owner",
            },
            {"source": "fixture"},
        ]
    )
    install_connection(monkeypatch, unchanged)
    assert storage.upsert_catalogue_app("run-3", app) == "unchanged"
    assert any("last_seen_run_id" in sql for sql, _ in unchanged.executed)
    assert not any("INSERT INTO indexing_outbox" in sql for sql, _ in unchanged.executed)


def test_tombstone_and_outbox_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(
        many=[
            [
                {"id": "app-001", "revision": 3, "checksum": "old", "payload": {}},
                {"id": "app-002", "revision": 2, "checksum": "old", "payload": {}},
            ],
            [{"id": 9, "app_id": "app-001", "operation": "delete", "attempts": 1}],
        ]
    )
    install_connection(monkeypatch, cursor)
    assert storage.tombstone_missing_apps("run-final", conn=FakeConnection(cursor)) == 2
    assert storage.pending_outbox(limit=25)[0]["id"] == 9
    assert sum("INSERT INTO indexing_outbox" in sql for sql, _ in cursor.executed) == 2
    assert cursor.executed[-1][1] == (10, 180, 25)
    assert "schema_version = '2.0'" in cursor.executed[0][0]


@pytest.mark.parametrize("visible", [True, False, None])
def test_store_projection_retains_visibility_without_indexing(
    monkeypatch: pytest.MonkeyPatch,
    visible: bool | None,
) -> None:
    app = StoreAppMetadata(store_id="Store", app_id="App", active=True, visible=visible)
    cursor = FakeCursor(one=[{"source": "offline"}, None])
    install_connection(monkeypatch, cursor)
    assert storage.upsert_catalogue_app("run-1", app) == "created"
    params = next(params for sql, params in cursor.executed if "INSERT INTO catalog_apps" in sql)
    assert params[3] == "hedge-store-v1"
    assert params[6] is (visible is True)
    assert params[7] is None  # registration is not an update timestamp
    assert params[-2:] == ("Store", "App")
    assert json.loads(params[4])["visible"] is visible
    assert any("INSERT INTO catalog_app_revisions" in sql for sql, _ in cursor.executed)
    assert not any("indexing_outbox" in sql for sql, _ in cursor.executed)

    cursor = FakeCursor(
        one=[
            {"source": "offline"},
            {
                "checksum": app.checksum,
                "revision": 1,
                "schema_version": "hedge-store-v1",
                "active": visible is True,
            },
        ]
    )
    install_connection(monkeypatch, cursor)
    assert storage.upsert_catalogue_app("run-2", app) == "unchanged"
    assert cursor.executed[-1][1][0] is (visible is True)


def test_profile_key_collision_cannot_overwrite_existing_data(monkeypatch) -> None:
    cursor = FakeCursor(
        one=[{"source": "offline"}, {"checksum": "old", "revision": 1, "schema_version": "2.0"}]
    )
    install_connection(monkeypatch, cursor)
    with pytest.raises(ValueError, match="different source profile"):
        storage.upsert_catalogue_app("run", StoreAppMetadata(store_id="Store", app_id="App"))
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in cursor.executed)


def test_store_registration_cannot_be_used_as_update_timestamp(monkeypatch) -> None:
    cursor = FakeCursor()
    install_connection(monkeypatch, cursor)
    with pytest.raises(ValueError, match="no confirmed source update timestamp"):
        storage.upsert_catalogue_app(
            "run",
            StoreAppMetadata(store_id="Store", app_id="App"),
            source_updated_at=datetime.now(UTC),
        )
    assert not cursor.executed


def test_outbox_completion_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(one=[{"operation": "upsert"}, {"id": 13}])
    install_connection(monkeypatch, cursor)
    claim = datetime.now(UTC)
    assert storage.complete_outbox_item(12, app_id="app-001", revision=7, claimed_at=claim)
    assert storage.fail_outbox_item(13, "temporary failure", claimed_at=claim)
    assert any("searchable_at = now()" in sql for sql, _ in cursor.executed)
    assert cursor.executed[-1][1] == ("temporary failure", 10, 13, claim)


def test_lexical_search_builds_all_typed_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(many=[[{"id": "app-001", "lexical_score": 0.8}]])
    install_connection(monkeypatch, cursor)
    filters = SearchFilters(
        semantic_uri="https://saref.etsi.org/core/Device",
        extension_uri="https://saref.etsi.org/saref4ener/",
        publisher="Synthetic",
        capabilities=["forecast"],
        tags=["energy"],
        protocols=["MQTT"],
        deployment_modes=["edge"],
        license_spdx="Apache-2.0",
        lifecycle_status="active",
        supported_languages=["en", "de"],
        data_classifications=["operational"],
    )
    rows = storage.lexical_search(
        "energy forecast",
        locale="de",
        filters=filters,
        limit=40,
    )
    assert rows[0]["id"] == "app-001"
    sql, params = cursor.executed[0]
    assert "jsonb_array_elements" in sql
    assert "websearch_to_tsquery" in sql
    assert params[-1] == 40


def test_catalogue_reads_and_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(
        one=[
            {"payload": {"id": "app-001"}},
            None,
            {"total": 2},
            {"revision": "rev-hash"},
        ],
        many=[[{"payload": {"id": "app-001"}}, {"payload": {"id": "app-002"}}]],
    )
    install_connection(monkeypatch, cursor)
    assert storage.get_catalogue_app("app-001") == {"id": "app-001"}
    assert storage.get_catalogue_app("missing", include_inactive=True) is None
    total, apps = storage.list_catalogue_apps(limit=2, offset=1)
    assert total == 2 and len(apps) == 2
    assert storage.current_catalogue_revision() == "rev-hash"
    assert all("schema_version = '2.0'" in sql for sql, _ in cursor.executed)


def test_impressions_events_and_kpis(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(
        one=[
            {"result_ids": ["app-001"]},
            {"id": 1},
            {"result_ids": ["app-001"]},
            None,
            {"accepted": 3, "dismissed": 1, "app_opened": 4},
            {"accepted": 0, "dismissed": 0, "app_opened": 0},
        ]
    )
    install_connection(monkeypatch, cursor)
    impression_id = storage.create_impression(
        session_id="raw-session",
        result_ids=["app-001"],
        locale="en",
        intent="search",
        request_id="req-1",
        timings={"retrieval_ms": 12.5},
    )
    assert impression_id.startswith("imp-")
    impression_params = cursor.executed[0][1]
    assert impression_params[1] != "raw-session" and len(impression_params[1]) == 64

    event = RecommendationEventRequest(
        impression_id=impression_id,
        idempotency_key="event-1",
        event_type="app_opened",
        app_id="app-001",
        occurred_at=datetime.now(UTC),
    )
    assert storage.record_recommendation_event(event)
    assert not storage.record_recommendation_event(event)
    assert storage.recommendation_kpis()["acceptance_rate"] == 0.75
    assert storage.recommendation_kpis()["acceptance_rate"] is None


def test_event_rejects_unknown_impression_and_unexposed_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = FakeCursor(one=[None])
    install_connection(monkeypatch, missing)
    event = RecommendationEventRequest(
        impression_id="imp-missing",
        idempotency_key="event-missing",
        event_type="app_opened",
        app_id="app-001",
    )
    with pytest.raises(LookupError, match="impression not found"):
        storage.record_recommendation_event(event)

    mismatch = FakeCursor(one=[{"result_ids": ["app-002"]}])
    install_connection(monkeypatch, mismatch)
    with pytest.raises(ValueError, match="not part of the impression"):
        storage.record_recommendation_event(event)


def test_data_retention_is_transactional_and_privacy_minimized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cursor = FakeCursor(rowcounts=[3, 8, 2])
    install_connection(monkeypatch, cursor)
    cutoff = datetime(2026, 7, 31, tzinfo=UTC)

    assert storage.apply_data_retention(as_of=cutoff) == {
        "aggregate_groups": 3,
        "expired_impressions": 8,
        "expired_transcripts": 2,
    }
    aggregate_sql = cursor.executed[0][0]
    assert "recommendation_daily_aggregates" in aggregate_sql
    assert "session_hash" not in aggregate_sql.split("INSERT INTO", 1)[1].split(")", 1)[0]
    assert all(params == (cutoff,) for _, params in cursor.executed)


@pytest.mark.parametrize("kind", ["delete", None])
def test_completion_never_marks_deleted_or_lost_claim_searchable(monkeypatch, kind):
    cursor = FakeCursor(one=[{"operation": kind} if kind else None])
    install_connection(monkeypatch, cursor)
    assert storage.complete_outbox_item(
        12, app_id="app-001", revision=7, claimed_at=datetime.now(UTC)
    ) is (kind is not None)
    assert not any("UPDATE catalog_apps" in sql for sql, _ in cursor.executed)


def test_outbox_backlog_explicit_recovery_and_authoritative_candidate_reads(monkeypatch):
    cursor = FakeCursor(
        one=[{"outstanding": 2, "exhausted": 1}, {"id": 12}, None],
        many=[[{"id": "app-001", "revision": 2, "payload": {}}]],
    )
    install_connection(monkeypatch, cursor)
    assert storage.outbox_status() == {"outstanding": 2, "exhausted": 1}
    assert storage.retry_outbox_item(12)
    assert not storage.retry_outbox_item(12)
    assert storage.get_catalogue_apps([]) == {}
    assert storage.get_catalogue_apps(["app-001"])["app-001"]["revision"] == 2


def test_index_lock_and_fenced_failed_acknowledgement(monkeypatch):
    cursor = FakeCursor(one=[{"id": "app-001"}, None])
    install_connection(monkeypatch, cursor)
    with storage.catalogue_index_app("app-001") as row:
        assert row == {"id": "app-001"}
    assert not storage.fail_outbox_item(12, "late failure", claimed_at=datetime.now(UTC))

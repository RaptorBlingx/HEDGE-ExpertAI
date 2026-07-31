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
    created = FakeCursor(one=[None])
    install_connection(monkeypatch, created)
    assert storage.upsert_catalogue_app("run-1", app) == "created"
    assert any("INSERT INTO indexing_outbox" in sql for sql, _ in created.executed)

    updated = FakeCursor(one=[{"checksum": "different", "revision": 4}])
    install_connection(monkeypatch, updated)
    assert storage.upsert_catalogue_app("run-2", app) == "updated"
    catalogue_params = next(
        params for sql, params in updated.executed if "INSERT INTO catalog_apps" in sql
    )
    assert catalogue_params[2] == 5

    unchanged = FakeCursor(one=[{"checksum": app.checksum, "revision": 5}])
    install_connection(monkeypatch, unchanged)
    assert storage.upsert_catalogue_app("run-3", app) == "unchanged"
    assert any("last_seen_run_id" in sql for sql, _ in unchanged.executed)
    assert not any("INSERT INTO indexing_outbox" in sql for sql, _ in unchanged.executed)


def test_tombstone_and_outbox_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor(
        many=[
            [{"id": "app-001", "revision": 3}, {"id": "app-002", "revision": 2}],
            [{"id": 9, "app_id": "app-001", "operation": "delete", "attempts": 1}],
        ]
    )
    install_connection(monkeypatch, cursor)
    assert storage.tombstone_missing_apps("run-final") == 2
    assert storage.pending_outbox(limit=25)[0]["id"] == 9
    assert sum("INSERT INTO indexing_outbox" in sql for sql, _ in cursor.executed) == 2
    assert cursor.executed[-1][1] == (25,)


def test_outbox_completion_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = FakeCursor()
    install_connection(monkeypatch, cursor)
    storage.complete_outbox_item(12, app_id="app-001", revision=7)
    storage.fail_outbox_item(13, "temporary failure")
    assert any("searchable_at = now()" in sql for sql, _ in cursor.executed)
    assert cursor.executed[-1][1] == ("temporary failure", 13)


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

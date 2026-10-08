"""Reconciliation against the guarded, disposable Phase 1 PostgreSQL fixture."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Event

import pytest
from hedge_shared import storage
from hedge_shared.store_v1 import StoreAppMetadata

from .test_store_v1_persistence import database as database
from .test_store_v1_persistence import migrate, rows

ROOT = Path(__file__).parents[2]
APP = ROOT / "services/metadata-ingest/app"
spec = importlib.util.spec_from_file_location(
    "snapshot_test_ingest", APP / "__init__.py", submodule_search_locations=[str(APP)]
)
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
snapshot = importlib.import_module("snapshot_test_ingest.snapshot")


@pytest.fixture
def migrated_database(database):
    migrate.main()
    return database


def published(app_id="A", **changes):
    return {"appId": app_id, "active": True, "visible": True, **changes}


def reconcile(records, *, store="Store-A", complete=True, allow_empty=False, source="offline"):
    return snapshot.reconcile_catalogue_snapshot(
        source,
        lambda: records,
        store_id=store,
        snapshot_complete=complete,
        allow_empty=allow_empty,
    )


def projection():
    return {t: rows(t) for t in ("catalog_apps", "catalog_app_revisions", "indexing_outbox")}


def app_row(app_id="A", store="Store-A"):
    key = StoreAppMetadata(store_id=store, app_id=app_id).id
    return next(r for r in rows("catalog_apps") if r["id"] == key)


def wait_for_blocked_lock(kind):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with storage.connection() as conn:
            waiting = conn.execute(
                "SELECT count(*) AS n FROM pg_locks WHERE locktype = %s AND NOT granted", (kind,)
            ).fetchone()["n"]
        if waiting:
            return
        time.sleep(0.01)
    pytest.fail(f"concurrent writer did not reach the {kind} lock")


def test_absence_is_scoped_to_native_store_and_preserves_synthetic(migrated_database):
    reconcile([published(), published("B")])
    reconcile([published(), published("B")], store="Store-B")
    unrelated = [r for r in rows("catalog_apps") if r["source_store_id"] != "Store-A"]
    result = reconcile([published()])
    assert result["status"] == "completed" and result["deleted"] == 1
    assert app_row("B")["active"] is False and app_row("B")["revision"] == 2
    assert [r for r in rows("catalog_apps") if r["source_store_id"] != "Store-A"] == unrelated
    revisions = [r for r in rows("catalog_app_revisions") if r["app_id"] == app_row("B")["id"]]
    assert {r["revision"] for r in revisions} == {1, 2}
    assert len(rows("indexing_outbox")) == 1  # original synthetic operation only


@pytest.mark.parametrize(
    "records,complete,quarantined",
    [
        ([published()], False, 0),
        ([published(), published("B", visible="false")], True, 1),
        ([published(), None], True, 1),
        ([published(), ["not", "an", "App"]], True, 1),
        ([published(), published(name="conflicting duplicate")], True, 2),
        ([published(), published("B", fkAppStoreId="Store-B")], True, 1),
        ([published(), {"name": "missing identity"}], True, 1),
    ],
)
def test_partial_or_quarantined_snapshots_cannot_retire(
    migrated_database, records, complete, quarantined
):
    reconcile([published(), published("B")])
    before = projection()
    result = reconcile(records, complete=complete)
    assert result["status"] == "partial" and result["deleted"] == 0
    assert result["quarantined"] == quarantined
    # Successful observations may advance last_seen_run_id; nothing is deactivated or revised.
    assert all(r["active"] for r in rows("catalog_apps"))
    assert rows("catalog_app_revisions") == before["catalog_app_revisions"]
    assert rows("indexing_outbox") == before["indexing_outbox"]
    assert storage.list_quarantined_items(run_id=result["run_id"])[0] == result["quarantined"]


@pytest.mark.parametrize("withdrawal", [{"visible": False}, {"active": False}])
def test_partial_snapshot_still_applies_explicit_publication_withdrawal(
    migrated_database, withdrawal
):
    reconcile([published(), published("B")])
    result = reconcile([published(**withdrawal), published("B", active="invalid")])
    assert result["status"] == "partial" and result["deleted"] == 0
    assert app_row()["active"] is False
    assert all(app_row()["payload"][flag] is value for flag, value in withdrawal.items())
    assert app_row()["revision"] == 2
    assert app_row("B")["active"] is True and app_row("B")["revision"] == 1


def test_empty_requires_complete_snapshot_and_deliberate_approval(migrated_database):
    reconcile([published(), published("B")])
    reconcile([published()], store="Store-B")
    before = projection()
    for complete, allow_empty in [(True, False), (False, True)]:
        result = reconcile([], complete=complete, allow_empty=allow_empty)
        assert result["status"] == "partial" and result["deleted"] == 0
        assert projection() == before
    result = reconcile([], allow_empty=True)
    assert result["deleted"] == 2 and result["status"] == "completed"
    assert app_row(store="Store-B")["active"] is True


@pytest.mark.parametrize("failure", ["fetch", "envelope"])
def test_failed_fetch_or_envelope_preserves_every_committed_row(migrated_database, failure):
    reconcile([published(), published("B")])
    before = projection()

    def fetch():
        if failure == "fetch":
            raise TimeoutError("page request failed")
        return {"apps": [published()]}

    with pytest.raises((TimeoutError, ValueError)):
        snapshot.reconcile_catalogue_snapshot(
            "offline", fetch, store_id="Store-A", snapshot_complete=True
        )
    assert projection() == before
    failed = storage.latest_ingestion_run()
    assert failed["status"] == "failed" and failed["deleted_count"] == failed["updated_count"] == 0


@pytest.mark.parametrize(
    "stage", ["upsert_catalogue_app", "tombstone_missing_apps", "complete_ingestion_run"]
)
def test_transaction_failure_rolls_back_projection_revisions_and_outbox(
    migrated_database, monkeypatch, stage
):
    fixtures = json.loads((ROOT / "services/mock-api/app/data/apps-v2.json").read_text())[:2]
    reconcile(fixtures, store=None)
    before = projection()
    changed = deepcopy(fixtures[0])
    changed["title"]["en"] = "Updated title"
    original = getattr(snapshot, stage)

    def fail_after_write(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("conn") is not None:
            raise RuntimeError("simulated transaction failure")
        return result

    monkeypatch.setattr(snapshot, stage, fail_after_write)
    with pytest.raises(RuntimeError, match="simulated"):
        reconcile([changed], store=None)
    assert projection() == before
    failed = storage.latest_ingestion_run()
    assert failed["status"] == "failed" and failed["created_count"] == failed["deleted_count"] == 0


def test_store_absence_withdrawal_and_identical_reappearance_are_revisioned(migrated_database):
    record = published()
    reconcile([record])
    reconcile([], allow_empty=True)
    assert reconcile([record])["updated"] == 1  # same checksum, but reactivation is a new revision
    assert app_row()["revision"] == 3 and app_row()["active"] is True
    reconcile([published(visible=False)])
    reconcile([record])
    assert reconcile([record])["unchanged"] == 1
    assert app_row()["revision"] == 5
    assert len(rows("indexing_outbox")) == 1  # Store indexing remains deliberately unwired


def test_synthetic_source_ownership_and_reappearance_enqueue_ordered_operations(migrated_database):
    fixtures = json.loads((ROOT / "services/mock-api/app/data/apps-v2.json").read_text())[:2]
    reconcile([fixtures[0]], store=None, source="mock-A")
    reconcile([fixtures[1]], store=None, source="mock-B")
    reconcile([published()])
    unrelated = [r for r in rows("catalog_apps") if r["id"] != fixtures[0]["id"]]
    reconcile([], store=None, source="mock-A", allow_empty=True)
    result = reconcile([fixtures[0]], store=None, source="mock-A")
    assert result["updated"] == 1
    assert [r for r in rows("catalog_apps") if r["id"] != fixtures[0]["id"]] == unrelated
    operations = sorted(
        (r["revision"], r["operation"])
        for r in rows("indexing_outbox")
        if r["app_id"] == fixtures[0]["id"]
    )
    assert operations == [(7, "upsert"), (8, "delete"), (9, "upsert")]
    collision = reconcile([fixtures[0]], store=None, source="mock-B")
    assert collision["status"] == "partial" and collision["quarantined"] == 1
    assert collision["deleted"] == 0
    assert [r for r in rows("catalog_apps") if r["id"] != fixtures[0]["id"]] == unrelated


def test_same_store_fetches_are_serialized_even_with_different_transport_sources(migrated_database):
    reconcile([published(), published("B")])
    first_fetch = Event()
    release = Event()
    second_fetch = Event()

    def fetch_first():
        first_fetch.set()
        assert release.wait(10)
        return [published(name="first snapshot")]

    def fetch_second():
        second_fetch.set()
        return [published(), published("B")]

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            snapshot.reconcile_catalogue_snapshot,
            "old-url",
            fetch_first,
            store_id="Store-A",
            snapshot_complete=True,
        )
        try:
            assert first_fetch.wait(5)
            second = pool.submit(
                snapshot.reconcile_catalogue_snapshot,
                "new-url",
                fetch_second,
                store_id="Store-A",
                snapshot_complete=True,
            )
            wait_for_blocked_lock("advisory")
            assert not second_fetch.is_set()
        finally:
            release.set()
        assert first.result(timeout=5)["deleted"] == 1
        assert second.result(timeout=5)["updated"] == 2
    assert second_fetch.is_set()
    assert app_row()["active"] is app_row("B")["active"] is True
    assert app_row()["revision"] == app_row("B")["revision"] == 3


def test_different_store_snapshot_can_complete_while_one_fetch_is_blocked(migrated_database):
    reconcile([published()], store="Store-B")
    fetching = Event()
    release = Event()

    def blocked_fetch():
        fetching.set()
        assert release.wait(10)
        return [published()]

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            snapshot.reconcile_catalogue_snapshot,
            "same-url",
            blocked_fetch,
            store_id="Store-A",
            snapshot_complete=True,
        )
        try:
            assert fetching.wait(5)
            second = pool.submit(
                reconcile, [], store="Store-B", allow_empty=True, source="same-url"
            )
            assert second.result(timeout=5)["deleted"] == 1
        finally:
            release.set()
        assert first.result(timeout=5)["created"] == 1
    assert app_row()["active"] is True and app_row(store="Store-B")["active"] is False


def test_concurrent_first_claim_cannot_transfer_synthetic_source_ownership(migrated_database):
    first_run = storage.create_ingestion_run("mock-A")
    second_run = storage.create_ingestion_run("mock-B")
    claimed = Event()
    release = Event()

    def claim_first():
        with storage.catalogue_snapshot("mock-A") as conn:
            action = storage.upsert_catalogue_app(first_run, migrated_database, conn=conn)
            claimed.set()
            assert release.wait(10)
            return action

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(claim_first)
        try:
            assert claimed.wait(5)
            second = pool.submit(storage.upsert_catalogue_app, second_run, migrated_database)
            wait_for_blocked_lock("transactionid")
        finally:
            release.set()
        assert first.result(timeout=5) == "unchanged"
        with pytest.raises(ValueError, match="different source"):
            second.result(timeout=5)
    row = next(r for r in rows("catalog_apps") if r["id"] == migrated_database.id)
    assert str(row["last_seen_run_id"]) == first_run and row["revision"] == 7
    assert len(rows("catalog_app_revisions")) == len(rows("indexing_outbox")) == 1

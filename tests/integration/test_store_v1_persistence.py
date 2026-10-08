"""Migration and source projection checks against an explicitly disposable DB.

Run with HEDGE_TEST_DATABASE_URL pointing to a database named hedge_phase1_test.
Each test creates and removes its own schema; no live services are needed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from hedge_shared import storage
from hedge_shared.models_v2 import AppMetadataV2, SearchFilters
from hedge_shared.store_v1 import StoreAppMetadata
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).parents[2]
MIGRATIONS = ROOT / "database/migrations"
spec = importlib.util.spec_from_file_location("store_test_migrate", ROOT / "database/migrate.py")
migrate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(migrate)


@pytest.fixture
def database(monkeypatch):
    dsn = os.getenv("HEDGE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("requires an explicitly disposable HEDGE_TEST_DATABASE_URL")
    schema = "store_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT current_database()").fetchone()[0] == "hedge_phase1_test"
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = make_conninfo(dsn, options=f"-c search_path={schema}")
    monkeypatch.setenv("DATABASE_URL", scoped)
    monkeypatch.setattr(migrate, "DATABASE_URL", scoped)
    try:
        with storage.connection() as conn:
            conn.execute((MIGRATIONS / "0001_initial.up.sql").read_text())
            fixtures = json.loads((ROOT / "services/mock-api/app/data/apps-v2.json").read_text())
            app = AppMetadataV2.model_validate(fixtures[0])
            payload = json.dumps(app.model_dump(mode="json", exclude={"checksum"}))
            conn.execute(
                """INSERT INTO catalog_apps
                    (id, checksum, revision, schema_version, payload, search_document, searchable_at)
                    VALUES (%s, %s, 7, '2.0', %s::jsonb, %s, now())""",
                (app.id, app.checksum, payload, app.to_index_text()),
            )
            conn.execute(
                """INSERT INTO catalog_app_revisions (app_id, revision, checksum, payload)
                    VALUES (%s, 7, %s, %s::jsonb)""",
                (app.id, app.checksum, payload),
            )
            conn.execute(
                """INSERT INTO indexing_outbox (app_id, revision, operation, payload, status)
                    VALUES (%s, 7, 'upsert', %s::jsonb, 'completed')""",
                (app.id, payload),
            )
        yield app
    finally:
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def rows(table):
    with storage.connection() as conn:
        return conn.execute(
            sql.SQL("SELECT * FROM {} ORDER BY 1").format(
                sql.Identifier(table),
            )
        ).fetchall()


def test_additive_migration_preserves_existing_data_and_runs_once(database) -> None:
    before = {t: rows(t) for t in ("catalog_apps", "catalog_app_revisions", "indexing_outbox")}
    migrate.main()
    migrate.main()
    after = rows("catalog_apps")[0]
    assert {k: after[k] for k in before["catalog_apps"][0]} == before["catalog_apps"][0]
    assert after["source_store_id"] is after["source_app_id"] is None
    assert rows("catalog_app_revisions") == before["catalog_app_revisions"]
    assert rows("indexing_outbox") == before["indexing_outbox"]
    assert storage.get_catalogue_app(database.id)["id"] == database.id
    assert len(rows("schema_migrations")) == 3


def test_composite_identity_and_synthetic_reads_remain_separate(database) -> None:
    migrate.main()
    run = storage.create_ingestion_run("offline-contract-fixture")
    apps = [
        StoreAppMetadata(
            store_id=store, app_id="Same-App", name="energy", active=True, visible=True
        )
        for store in ("Store-A", "Store-B")
    ]
    for app in apps:
        assert storage.upsert_catalogue_app(run, app) == "created"
    assert len(rows("catalog_apps")) == 3
    assert {r["source_store_id"] for r in rows("catalog_apps") if r["source_app_id"]} == {
        "Store-A",
        "Store-B",
    }
    assert len(rows("indexing_outbox")) == 1  # existing synthetic operation only
    assert all(storage.get_catalogue_app(app.id, include_inactive=True) is None for app in apps)
    assert storage.list_catalogue_apps(limit=10)[0] == 1
    assert storage.lexical_search("energy", locale="en", filters=SearchFilters(), limit=10)
    assert all(
        r["id"] == database.id
        for r in storage.lexical_search(
            "energy",
            locale="en",
            filters=SearchFilters(),
            limit=10,
        )
    )
    # The legacy synthetic reconciler cannot retire offline Store source rows.
    with storage.catalogue_snapshot("offline-contract-fixture") as conn:
        storage.tombstone_missing_apps(run, conn=conn)
    assert all(r["active"] for r in rows("catalog_apps") if r["source_app_id"])


def test_publication_withdrawal_and_sparse_metadata_revisions(database) -> None:
    migrate.main()
    run = storage.create_ingestion_run("offline")
    published = StoreAppMetadata(store_id="Store", app_id="App", active=True, visible=True)
    assert storage.upsert_catalogue_app(run, published) == "created"
    withdrawn = StoreAppMetadata(store_id="Store", app_id="App", active=True, visible=False)
    assert storage.upsert_catalogue_app(run, withdrawn) == "updated"
    assert storage.upsert_catalogue_app(run, withdrawn) == "unchanged"
    with storage.connection() as conn:
        row = conn.execute("SELECT * FROM catalog_apps WHERE id = %s", (published.id,)).fetchone()
    assert row["revision"] == 2 and row["active"] is False
    assert row["payload"]["visible"] is False and row["payload"]["name"] is None
    restored = StoreAppMetadata.model_validate(row["payload"])
    assert restored.id == withdrawn.id and restored.checksum == row["checksum"]
    assert not restored.public_eligible
    assert row["searchable_at"] is row["source_updated_at"] is None
    assert storage.upsert_catalogue_app(run, published) == "updated"
    assert len(rows("indexing_outbox")) == 1
    revisions = [r for r in rows("catalog_app_revisions") if r["app_id"] == published.id]
    assert [r["revision"] for r in revisions] == [1, 2, 3]


def test_native_identity_constraints_and_lossless_downgrade_guard(database) -> None:
    migrate.main()
    run = storage.create_ingestion_run("offline")
    app = StoreAppMetadata(store_id="Store", app_id="App")
    storage.upsert_catalogue_app(run, app)
    with pytest.raises(psycopg.errors.UniqueViolation), storage.connection() as conn:
        conn.execute(
            """INSERT INTO catalog_apps
                (id, checksum, revision, schema_version, payload, search_document,
                 source_store_id, source_app_id)
                VALUES ('other-key', %s, 1, 'hedge-store-v1', '{}'::jsonb, '', 'Store', 'App')""",
            (app.checksum,),
        )
    with pytest.raises(psycopg.errors.CheckViolation), storage.connection() as conn:
        conn.execute("UPDATE catalog_apps SET source_store_id = NULL WHERE id = %s", (app.id,))
    before = rows("catalog_apps")
    with (
        pytest.raises(psycopg.errors.RaiseException, match="preserve them"),
        storage.connection() as conn,
    ):
        conn.execute((MIGRATIONS / "0003_store_identity.down.sql").read_text())
    assert rows("catalog_apps") == before


def test_empty_source_downgrade_preserves_synthetic_rows(database) -> None:
    migrate.main()
    with storage.connection() as conn:
        conn.execute((MIGRATIONS / "0003_store_identity.down.sql").read_text())
    assert storage.get_catalogue_app(database.id)["id"] == database.id
    migrate.main()
    assert storage.list_catalogue_apps(limit=10)[0] == 1


def test_concurrent_first_insert_is_one_revision(database) -> None:
    migrate.main()
    run = storage.create_ingestion_run("offline")
    app = StoreAppMetadata(store_id="Store", app_id="Concurrent", active=True, visible=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: storage.upsert_catalogue_app(run, app), range(8)))
    assert results.count("created") == 1 and results.count("unchanged") == 7
    assert len([r for r in rows("catalog_app_revisions") if r["app_id"] == app.id]) == 1

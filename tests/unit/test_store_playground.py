"""Resource guards for the manual offline runner; business paths run in diagnostics."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("test_manual_store_runner", ROOT / "scripts/store_v1_playground.py")
playground = importlib.util.module_from_spec(spec)
spec.loader.exec_module(playground)


@pytest.mark.parametrize(("key", "url"), [
    ("DATABASE_URL", "postgresql://postgres@database/hedge"),
    ("DATABASE_URL", "postgresql://postgres@postgres/hedge_phase1_test"),
    ("DATABASE_URL", ""),
    ("HEDGE_TEST_QDRANT_URL", "http://localhost:6333"),
    ("HEDGE_TEST_QDRANT_URL", "https://store.example.invalid"),
    ("VALKEY_SESSION_URL", "redis://valkey-cache:6379/0"),
    ("VALKEY_SESSION_URL", "redis://sessions:6379/1"),
])
def test_guard_rejects_demo_or_external_endpoints_before_resource_access(monkeypatch, key, url):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres@database/hedge_phase1_test")
    monkeypatch.setenv("HEDGE_TEST_QDRANT_URL", "http://vectors:6333")
    monkeypatch.setenv("VALKEY_SESSION_URL", "redis://sessions:6379/0")
    monkeypatch.setenv(key, url)
    with pytest.raises(ValueError, match="disposable resources"):
        playground.require_isolation()


def test_guard_rejects_populated_database_before_migrations_or_fixture_ingestion(monkeypatch):
    from contextlib import contextmanager

    from hedge_shared import storage

    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres@database/hedge_phase1_test")
    monkeypatch.setenv("HEDGE_TEST_QDRANT_URL", "http://vectors:6333")
    monkeypatch.setenv("VALKEY_SESSION_URL", "redis://sessions:6379/0")

    class Connection:
        def execute(self, query):
            return self

        def fetchone(self):
            return {"current_database": "hedge_phase1_test", "existing": "catalog_apps"}

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(storage, "connection", connection)
    with pytest.raises(ValueError, match="fresh disposable database"), playground.offline_playground():
        pytest.fail("should never migrate or initialize a populated database")

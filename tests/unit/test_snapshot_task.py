"""The scheduled job must use safe reconciliation before index delivery."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

APP = Path(__file__).parents[2] / "services/metadata-ingest/app"
spec = importlib.util.spec_from_file_location(
    "snapshot_task_ingest", APP / "__init__.py", submodule_search_locations=[str(APP)]
)
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
ingest = importlib.import_module("snapshot_task_ingest.tasks.ingest")


@pytest.mark.parametrize("delivery_failed", [0, 1])
def test_job_gates_completeness_and_records_delivery_failure(monkeypatch, delivery_failed):
    monkeypatch.setattr(ingest, "HEDGE_API_URL", "")

    def fetch():
        return []

    monkeypatch.setattr(
        ingest, "get_client", lambda **kwargs: SimpleNamespace(fetch_all_apps=fetch)
    )
    completed = []

    def reconcile(source, fetch_apps, **kwargs):
        assert source == ingest.MOCK_API_URL
        assert fetch_apps is fetch
        assert kwargs == {"snapshot_complete": True}
        return {
            "run_id": "run",
            "status": "completed",
            "fetched": 2,
            "created": 1,
            "updated": 0,
            "unchanged": 1,
            "quarantined": 0,
            "deleted": 0,
        }

    monkeypatch.setattr(ingest, "reconcile_catalogue_snapshot", reconcile)
    monkeypatch.setattr(
        ingest,
        "deliver_pending_outbox",
        lambda **kwargs: {"delivered": 1, "failed": delivery_failed},
    )
    monkeypatch.setattr(
        ingest, "complete_ingestion_run", lambda *args, **kwargs: completed.append(kwargs)
    )
    result = ingest.ingest_all.run()
    assert result["status"] == ("partial" if delivery_failed else "completed")
    assert len(completed) == delivery_failed
    if completed:
        assert completed[0]["status"] == "partial" and completed[0]["deleted"] == 0


def test_reconciliation_failure_retries_without_index_delivery(monkeypatch):
    def fail(*args, **kwargs):
        raise TimeoutError("source failed")

    def retry(*, exc, countdown):
        assert isinstance(exc, TimeoutError) and countdown == 60
        raise RuntimeError("retry requested")

    def unexpected_delivery(**kwargs):
        pytest.fail("failed reconciliation must not deliver index operations")

    monkeypatch.setattr(ingest, "reconcile_catalogue_snapshot", fail)
    monkeypatch.setattr(ingest.ingest_all, "retry", retry)
    monkeypatch.setattr(ingest, "deliver_pending_outbox", unexpected_delivery)
    with pytest.raises(RuntimeError, match="retry requested"):
        ingest.ingest_all.run()


def test_configured_store_is_blocked_before_fetch_database_or_delivery(monkeypatch):
    monkeypatch.setattr(ingest, "HEDGE_API_URL", "https://store.invalid/backend/api/v1")

    def unexpected(*args, **kwargs):
        pytest.fail("Store job must not access the network, database or index")

    for name in (
        "get_client",
        "reconcile_catalogue_snapshot",
        "deliver_pending_outbox",
        "complete_ingestion_run",
    ):
        monkeypatch.setattr(ingest, name, unexpected)
    result = ingest.ingest_all.run()
    assert result["status"] == "disabled" and "not enabled" in result["reason"]


@pytest.mark.parametrize("ack", [{}, {"applied": True}, {"applied": 2}])
def test_bad_index_acknowledgement_keeps_durable_work_for_retry(monkeypatch, ack):
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    claim = {
        "id": 1,
        "app_id": "test-app",
        "revision": 2,
        "operation": "delete",
        "updated_at": datetime.now(UTC),
    }
    claims = iter([[claim], []])
    monkeypatch.setattr(ingest, "pending_outbox", lambda **kwargs: next(claims))
    monkeypatch.setattr(ingest, "outbox_status", lambda: {"outstanding": 1, "exhausted": 0})
    response = MagicMock()
    response.json.return_value = ack
    monkeypatch.setattr(ingest.httpx, "post", lambda *a, **k: response)
    failed, completed = MagicMock(), MagicMock()
    monkeypatch.setattr(ingest, "fail_outbox_item", failed)
    monkeypatch.setattr(ingest, "complete_outbox_item", completed)
    assert ingest.deliver_pending_outbox(limit=2)["failed"] == 1
    completed.assert_not_called()
    assert failed.call_args.kwargs["claimed_at"] == claim["updated_at"]

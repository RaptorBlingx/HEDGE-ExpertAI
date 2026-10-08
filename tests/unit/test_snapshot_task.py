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


@pytest.mark.parametrize("hedge_url", ["", "https://legacy.invalid"])
@pytest.mark.parametrize("delivery_failed", [0, 1])
def test_job_gates_completeness_and_records_delivery_failure(
    monkeypatch, hedge_url, delivery_failed
):
    monkeypatch.setattr(ingest, "HEDGE_API_URL", hedge_url)

    def fetch():
        return []

    monkeypatch.setattr(
        ingest, "get_client", lambda **kwargs: SimpleNamespace(fetch_all_apps=fetch)
    )
    completed = []

    def reconcile(source, fetch_apps, **kwargs):
        assert source == (hedge_url or ingest.MOCK_API_URL)
        assert fetch_apps is fetch
        assert kwargs == {"snapshot_complete": not bool(hedge_url)}
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

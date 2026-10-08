"""Explicit replay reaches the existing admin boundary with validated identity."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[2]


def service(name, path):
    package = ModuleType(name)
    package.__path__ = [str(ROOT / path)]
    sys.modules[name] = package
    return importlib.import_module(name + ".routes")


gateway = service("recovery_gateway", "services/gateway/app")
ingestion = service("recovery_ingestion", "services/metadata-ingest/app")
PATH = "/api/v2/ingestion/outbox/replay"


@pytest.fixture
def gateway_client(monkeypatch):
    monkeypatch.setenv("ENABLE_RBAC", "true")
    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request, next_handler):
        # This fixture tests the existing role boundary, not real OIDC validation.
        if request.headers.get("X-Test-Admin") == "yes":
            request.state.user = SimpleNamespace(roles=["admin"])
        return await next_handler(request)

    app.include_router(gateway.router)
    return TestClient(app)


@pytest.mark.parametrize("suffix", ["", "?outbox_id=27"])
def test_gateway_forwards_explicit_recovery_without_changing_normal_replay(
    gateway_client, monkeypatch, suffix
):
    upstream = AsyncMock(return_value=JSONResponse({"status": "queued"}, status_code=202))
    monkeypatch.setattr(gateway, "_post_json", upstream)
    response = gateway_client.post(PATH + suffix, headers={"X-Test-Admin": "yes"})
    assert response.status_code == 202
    assert upstream.call_args.args[0] == gateway.METADATA_INGEST_URL + PATH + suffix


@pytest.mark.parametrize(
    "authorized,suffix,status", [(False, "?outbox_id=27", 401), (True, "?outbox_id=0", 422)]
)
def test_recovery_keeps_admin_and_query_validation_guards(
    gateway_client, monkeypatch, authorized, suffix, status
):
    upstream = AsyncMock()
    monkeypatch.setattr(gateway, "_post_json", upstream)
    response = gateway_client.post(
        PATH + suffix, headers={"X-Test-Admin": "yes"} if authorized else {}
    )
    assert response.status_code == status
    upstream.assert_not_called()


@pytest.mark.parametrize("released", [True, False])
def test_ingestion_releases_only_exhausted_work_before_queuing(monkeypatch, released):
    app = FastAPI()
    app.include_router(ingestion.router)
    release = MagicMock(return_value=released)
    queue = MagicMock(return_value=SimpleNamespace(id="test-task"))
    monkeypatch.setattr(ingestion, "retry_outbox_item", release)
    monkeypatch.setattr(ingestion.deliver_outbox_task, "delay", queue)
    response = TestClient(app).post(PATH + "?outbox_id=27")
    assert response.status_code == (202 if released else 409)
    release.assert_called_once_with(27)
    assert queue.call_count == int(released)

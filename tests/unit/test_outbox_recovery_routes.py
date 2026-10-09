"""Explicit replay reaches the existing admin boundary with validated identity."""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import jwt
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
middleware = importlib.import_module("recovery_gateway.middleware")
ingestion = service("recovery_ingestion", "services/metadata-ingest/app")
PATH = "/api/v2/ingestion/outbox/replay"
KEY = "test-only-admin-key"
JWT_SECRET = "test-only-signing-secret-with-at-least-32-bytes"


def bearer(role):
    token = jwt.encode(
        {"sub": "tester", "aud": "hedge-expert-api", "exp": int(time.time()) + 60, "roles": [role]},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


@pytest.fixture(autouse=True)
def admin_configuration(monkeypatch):
    monkeypatch.setenv("GATEWAY_API_KEY", KEY)
    monkeypatch.setenv("OAUTH_ENABLED", "true")
    monkeypatch.setenv("OAUTH_SHARED_SECRET", JWT_SECRET)
    monkeypatch.setenv("OAUTH_JWT_ALGORITHMS", "HS256")
    monkeypatch.setenv("OAUTH_AUDIENCE", "hedge-expert-api")
    monkeypatch.setenv("OAUTH_ISSUER", "")
    monkeypatch.setenv("RBAC_ADMIN_ROLES", "admin,administrator")


@pytest.fixture
def gateway_client(monkeypatch):
    monkeypatch.setenv("ENABLE_RBAC", "true")
    app = FastAPI()

    app.add_middleware(middleware.APIKeyMiddleware)
    app.add_middleware(middleware.JWTAuthMiddleware)
    app.include_router(gateway.router)
    return TestClient(app)


@pytest.mark.parametrize("suffix", ["", "?outbox_id=27"])
@pytest.mark.parametrize("rbac", ["true", "false"])
@pytest.mark.parametrize("headers", [bearer("admin"), {"X-API-Key": KEY}])
def test_gateway_forwards_explicit_recovery_without_changing_normal_replay(
    gateway_client, monkeypatch, suffix, rbac, headers
):
    monkeypatch.setenv("ENABLE_RBAC", rbac)
    upstream = AsyncMock(return_value=JSONResponse({"status": "queued"}, status_code=202))
    monkeypatch.setattr(gateway, "_post_json", upstream)
    response = gateway_client.post(PATH + suffix, headers=headers)
    assert response.status_code == 202
    assert upstream.call_args.args[0] == gateway.METADATA_INGEST_URL + PATH + suffix
    assert upstream.call_args.kwargs["headers"] == {"X-API-Key": KEY}


@pytest.mark.parametrize(
    "authorized,suffix,status", [(False, "?outbox_id=27", 401), (True, "?outbox_id=0", 422)]
)
def test_recovery_keeps_admin_and_query_validation_guards(
    gateway_client, monkeypatch, authorized, suffix, status
):
    upstream = AsyncMock()
    monkeypatch.setattr(gateway, "_post_json", upstream)
    response = gateway_client.post(PATH + suffix, headers=bearer("admin") if authorized else {})
    assert response.status_code == status
    upstream.assert_not_called()


@pytest.mark.parametrize("path", [PATH, "/api/v2/ingestion/runs", "/api/v1/ingest/trigger"])
@pytest.mark.parametrize("rbac", ["true", "false"])
@pytest.mark.parametrize(
    "headers,status",
    [
        ({}, 401),
        (bearer("analyst"), 403),
        ({"Authorization": "Bearer invalid"}, 401),
        ({"X-API-Key": "incorrect"}, 401),
    ],
)
def test_gateway_mutations_reject_unauthorized_callers(
    gateway_client, monkeypatch, path, rbac, headers, status
):
    monkeypatch.setenv("ENABLE_RBAC", rbac)
    upstream = AsyncMock()
    monkeypatch.setattr(gateway, "_post_json", upstream)
    client_factory = MagicMock()
    monkeypatch.setattr(gateway.httpx, "AsyncClient", client_factory)
    assert gateway_client.post(path, headers=headers).status_code == status
    upstream.assert_not_called()
    client_factory.assert_not_called()


@pytest.mark.parametrize("rbac", ["true", "false"])
def test_gateway_cannot_be_opened_by_unconfigured_key(gateway_client, monkeypatch, rbac):
    monkeypatch.setenv("ENABLE_RBAC", rbac)
    monkeypatch.delenv("GATEWAY_API_KEY")
    upstream = AsyncMock()
    monkeypatch.setattr(gateway, "_post_json", upstream)
    assert gateway_client.post(PATH).status_code == 401
    assert gateway_client.post(PATH, headers=bearer("admin")).status_code == 503
    upstream.assert_not_called()


def test_bearer_without_oauth_validation_cannot_authorize_replay(gateway_client, monkeypatch):
    monkeypatch.setenv("OAUTH_ENABLED", "false")
    monkeypatch.setenv("ENABLE_RBAC", "false")
    monkeypatch.delenv("GATEWAY_API_KEY")
    assert gateway_client.post(PATH, headers=bearer("admin")).status_code == 401


def test_configured_admin_roles_apply_with_rbac_disabled(gateway_client, monkeypatch):
    monkeypatch.setenv("ENABLE_RBAC", "false")
    monkeypatch.setenv("RBAC_ADMIN_ROLES", "operator")
    upstream = AsyncMock(return_value=JSONResponse({"status": "queued"}, status_code=202))
    monkeypatch.setattr(gateway, "_post_json", upstream)
    assert gateway_client.post(PATH, headers=bearer("admin")).status_code == 403
    upstream.assert_not_called()
    assert gateway_client.post(PATH, headers=bearer("operator")).status_code == 202


@pytest.mark.parametrize("path", [PATH, "/api/v2/ingestion/runs", "/api/v1/ingest/trigger"])
@pytest.mark.parametrize(
    "key,headers,status",
    [
        (KEY, {}, 401),
        (KEY, {"X-API-Key": "incorrect"}, 401),
        (KEY, bearer("admin"), 401),
        ("", {}, 503),
        ("", {"X-API-Key": KEY}, 503),
    ],
)
def test_internal_mutations_fail_before_database_or_queue_work(
    monkeypatch, path, key, headers, status
):
    monkeypatch.setenv("GATEWAY_API_KEY", key)
    app = FastAPI()
    app.include_router(ingestion.router)
    release, replay, ingest = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(ingestion, "retry_outbox_item", release)
    monkeypatch.setattr(ingestion.deliver_outbox_task, "delay", replay)
    monkeypatch.setattr(ingestion.ingest_all, "delay", ingest)
    assert TestClient(app).post(path, headers=headers).status_code == status
    release.assert_not_called()
    replay.assert_not_called()
    ingest.assert_not_called()


@pytest.mark.parametrize("path", ["/api/v2/ingestion/runs", "/api/v1/ingest/trigger"])
def test_internal_ingestion_with_admin_key_remains_available(monkeypatch, path):
    app = FastAPI()
    app.include_router(ingestion.router)
    queue = MagicMock(return_value=SimpleNamespace(id="test-task"))
    monkeypatch.setattr(ingestion.ingest_all, "delay", queue)
    assert TestClient(app).post(path, headers={"X-API-Key": KEY}).status_code in (200, 202)
    queue.assert_called_once()


def test_gateway_admin_replay_reaches_protected_internal_boundary(gateway_client, monkeypatch):
    app = FastAPI()
    app.include_router(ingestion.router)
    release = MagicMock(return_value=True)
    queue = MagicMock(return_value=SimpleNamespace(id="test-task"))
    monkeypatch.setattr(ingestion, "retry_outbox_item", release)
    monkeypatch.setattr(ingestion.deliver_outbox_task, "delay", queue)
    original_client = httpx.AsyncClient

    def internal_client():
        return original_client(transport=httpx.ASGITransport(app=app))

    monkeypatch.setattr(gateway.httpx, "AsyncClient", internal_client)
    assert gateway_client.post(PATH + "?outbox_id=27", headers=bearer("admin")).status_code == 202
    release.assert_called_once_with(27)
    queue.assert_called_once()


@pytest.mark.parametrize("released", [True, False])
def test_ingestion_releases_only_exhausted_work_before_queuing(monkeypatch, released):
    app = FastAPI()
    app.include_router(ingestion.router)
    release = MagicMock(return_value=released)
    queue = MagicMock(return_value=SimpleNamespace(id="test-task"))
    monkeypatch.setattr(ingestion, "retry_outbox_item", release)
    monkeypatch.setattr(ingestion.deliver_outbox_task, "delay", queue)
    response = TestClient(app).post(PATH + "?outbox_id=27", headers={"X-API-Key": KEY})
    assert response.status_code == (202 if released else 409)
    release.assert_called_once_with(27)
    assert queue.call_count == int(released)

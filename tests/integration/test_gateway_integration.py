"""Integration tests for HEDGE-ExpertAI gateway routing and service wiring.

Tests exercise the gateway FastAPI app with mocked backend services,
verifying that routing, middleware, and error handling work end-to-end.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import jwt

# Load gateway app module via sys.path manipulation (avoids `app` namespace collisions)
_gw_dir = Path(__file__).resolve().parent.parent.parent / "services" / "gateway"
sys.path.insert(0, str(_gw_dir))
import app.main as _gw_main  # noqa: E402
import app.routes as _gw_routes  # noqa: E402
sys.path.pop(0)

from fastapi.testclient import TestClient  # noqa: E402

_gateway_app = _gw_main.app


class _AsyncClientStub:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return self._response

    async def get(self, *args, **kwargs):
        return self._response


def _make_token(roles: list[str] | None = None) -> str:
    now = int(time.time())
    claims = {
        "sub": "tester",
        "aud": "hedge-expert-api",
        "exp": now + 3600,
        "iat": now,
        "realm_access": {"roles": roles or []},
    }
    return jwt.encode(claims, "test-secret", algorithm="HS256")


@pytest.fixture()
def client():
    """Create a test client for the gateway app."""
    return TestClient(_gateway_app)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
class TestGatewayHealth:
    """Test the /health aggregation endpoint."""

    def test_health_returns_gateway_ok(self, client):
        with patch.object(_gw_routes, "httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("Connection refused")
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["service"] == "gateway"
            assert "services" in data

    def test_health_reports_degraded_when_service_down(self, client):
        with patch.object(_gw_routes, "httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("Connection refused")
            resp = client.get("/health")
            data = resp.json()
            assert data["status"] == "degraded"


# ---------------------------------------------------------------------------
# Proxy routes
# ---------------------------------------------------------------------------
class TestGatewayProxy:
    """Test proxy routes forward correctly."""

    def test_chat_proxy_returns_502_on_backend_failure(self, client):
        class _FailingAsyncClient:
            async def __aenter__(self):
                raise Exception("Connection refused")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch.object(_gw_routes.httpx, "AsyncClient", return_value=_FailingAsyncClient()):
            resp = client.post("/api/v1/chat", json={"message": "hello"})
            assert resp.status_code == 502
            assert "unavailable" in resp.json()["detail"].lower()

    def test_search_proxy_returns_502_on_backend_failure(self, client):
        class _FailingAsyncClient:
            async def __aenter__(self):
                raise Exception("Connection refused")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        with patch.object(_gw_routes.httpx, "AsyncClient", return_value=_FailingAsyncClient()):
            resp = client.post("/api/v1/apps/search", json={"query": "energy"})
            assert resp.status_code == 502

    def test_chat_proxy_forwards_response(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "session_id": "abc",
            "message": "Hello!",
            "intent": "greeting",
            "apps": [],
        }
        with patch.object(_gw_routes.httpx, "AsyncClient", return_value=_AsyncClientStub(mock_resp)):
            resp = client.post("/api/v1/chat", json={"message": "hi"})
            assert resp.status_code == 200
            assert resp.json()["message"] == "Hello!"

    def test_ingest_trigger_proxy(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "triggered", "task_id": "xyz"}
        with patch.object(_gw_routes.httpx, "AsyncClient", return_value=_AsyncClientStub(mock_resp)):
            resp = client.post("/api/v1/ingest/trigger")
            assert resp.status_code == 200
            assert resp.json()["status"] == "triggered"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class TestGatewayMiddleware:
    """Test that middleware is applied correctly."""

    def test_security_headers_present(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_request_id_header_present(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Request-ID") is not None

    def test_custom_request_id_echoed(self, client):
        resp = client.get("/health", headers={"X-Request-ID": "test-123"})
        assert resp.headers.get("X-Request-ID") == "test-123"


class TestGatewayRBAC:
    def test_public_route_stays_open_when_rbac_enabled(self, client, monkeypatch):
        monkeypatch.setenv("OAUTH_ENABLED", "true")
        monkeypatch.setenv("ENABLE_RBAC", "true")
        monkeypatch.setenv("OAUTH_SHARED_SECRET", "test-secret")
        monkeypatch.setenv("OAUTH_JWT_ALGORITHMS", "HS256")
        monkeypatch.setenv("OAUTH_AUDIENCE", "hedge-expert-api")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "session_id": "abc",
            "message": "Hello!",
            "intent": "greeting",
            "apps": [],
        }

        with patch.object(_gw_routes.httpx, "AsyncClient", return_value=_AsyncClientStub(mock_resp)):
            resp = client.post("/api/v1/chat", json={"message": "hi"})

        assert resp.status_code == 200
        assert resp.json()["message"] == "Hello!"

    def test_admin_route_requires_token_when_rbac_enabled(self, client, monkeypatch):
        monkeypatch.setenv("OAUTH_ENABLED", "true")
        monkeypatch.setenv("ENABLE_RBAC", "true")
        monkeypatch.setenv("OAUTH_SHARED_SECRET", "test-secret")
        monkeypatch.setenv("OAUTH_JWT_ALGORITHMS", "HS256")
        monkeypatch.setenv("OAUTH_AUDIENCE", "hedge-expert-api")

        resp = client.post("/api/v1/ingest/trigger")
        assert resp.status_code == 401

    def test_admin_route_rejects_wrong_role(self, client, monkeypatch):
        monkeypatch.setenv("OAUTH_ENABLED", "true")
        monkeypatch.setenv("ENABLE_RBAC", "true")
        monkeypatch.setenv("OAUTH_SHARED_SECRET", "test-secret")
        monkeypatch.setenv("OAUTH_JWT_ALGORITHMS", "HS256")
        monkeypatch.setenv("OAUTH_AUDIENCE", "hedge-expert-api")

        token = _make_token(["analyst"])
        resp = client.post("/api/v1/ingest/trigger", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_admin_route_accepts_admin_role(self, client, monkeypatch):
        monkeypatch.setenv("OAUTH_ENABLED", "true")
        monkeypatch.setenv("ENABLE_RBAC", "true")
        monkeypatch.setenv("OAUTH_SHARED_SECRET", "test-secret")
        monkeypatch.setenv("OAUTH_JWT_ALGORITHMS", "HS256")
        monkeypatch.setenv("OAUTH_AUDIENCE", "hedge-expert-api")

        token = _make_token(["admin"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "triggered", "task_id": "xyz"}

        with patch.object(_gw_routes.httpx, "AsyncClient", return_value=_AsyncClientStub(mock_resp)):
            resp = client.post("/api/v1/ingest/trigger", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"

    def test_analyst_route_accepts_analyst_role(self, client, monkeypatch):
        monkeypatch.setenv("OAUTH_ENABLED", "true")
        monkeypatch.setenv("ENABLE_RBAC", "true")
        monkeypatch.setenv("OAUTH_SHARED_SECRET", "test-secret")
        monkeypatch.setenv("OAUTH_JWT_ALGORITHMS", "HS256")
        monkeypatch.setenv("OAUTH_AUDIENCE", "hedge-expert-api")

        token = _make_token(["analyst"])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"total_click": 1, "total_accept": 1, "total_dismiss": 0}

        with patch.object(_gw_routes.httpx, "AsyncClient", return_value=_AsyncClientStub(mock_resp)):
            resp = client.get("/api/v1/feedback/stats", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200

    def test_invalid_bearer_token_rejected(self, client, monkeypatch):
        monkeypatch.setenv("OAUTH_ENABLED", "true")
        monkeypatch.setenv("ENABLE_RBAC", "true")
        monkeypatch.setenv("OAUTH_SHARED_SECRET", "test-secret")
        monkeypatch.setenv("OAUTH_JWT_ALGORITHMS", "HS256")
        monkeypatch.setenv("OAUTH_AUDIENCE", "hedge-expert-api")

        resp = client.post("/api/v1/ingest/trigger", headers={"Authorization": "Bearer invalid-token"})
        assert resp.status_code == 401

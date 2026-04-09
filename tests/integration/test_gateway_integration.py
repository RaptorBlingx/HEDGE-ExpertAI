"""Integration tests for HEDGE-ExpertAI gateway routing and service wiring.

Tests exercise the gateway FastAPI app with mocked backend services,
verifying that routing, middleware, and error handling work end-to-end.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Load gateway app module via sys.path manipulation (avoids `app` namespace collisions)
_gw_dir = Path(__file__).resolve().parent.parent.parent / "services" / "gateway"
sys.path.insert(0, str(_gw_dir))
import app.main as _gw_main  # noqa: E402
import app.routes as _gw_routes  # noqa: E402
sys.path.pop(0)

from fastapi.testclient import TestClient  # noqa: E402

_gateway_app = _gw_main.app


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
        with patch.object(_gw_routes, "httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("Connection refused")
            resp = client.post("/api/v1/chat", json={"message": "hello"})
            assert resp.status_code == 502
            assert "unavailable" in resp.json()["detail"].lower()

    def test_search_proxy_returns_502_on_backend_failure(self, client):
        with patch.object(_gw_routes, "httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("Connection refused")
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
        with patch.object(_gw_routes, "httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_resp
            resp = client.post("/api/v1/chat", json={"message": "hi"})
            assert resp.status_code == 200
            assert resp.json()["message"] == "Hello!"

    def test_ingest_trigger_proxy(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "triggered", "task_id": "xyz"}
        with patch.object(_gw_routes, "httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_resp
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

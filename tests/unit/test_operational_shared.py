"""Tests for shared configuration, bounded metrics, and health helpers."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from hedge_shared.config import Settings
from hedge_shared.metrics import MetricsMiddleware, _fallback_route, metrics
from hedge_shared.utils import create_health_dict, setup_logging


def test_settings_defaults_and_real_store_precedence() -> None:
    defaults = Settings(_env_file=None)
    assert defaults.EMBEDDING_MODEL == "intfloat/multilingual-e5-small"
    assert defaults.EMBEDDING_MODEL_REVISION == "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    assert defaults.VALKEY_QUEUE_URL == "redis://valkey-queue:6379/0"
    assert defaults.app_store_url == defaults.MOCK_API_URL

    real = Settings(
        _env_file=None,
        HEDGE_API_URL="https://api.example.invalid/v2",
        MOCK_API_URL="https://fixtures.example.invalid",
    )
    assert real.app_store_url == "https://api.example.invalid/v2"


def test_fallback_route_bounds_dynamic_identifiers() -> None:
    route = _fallback_route("/api/v2/apps/app-001/sessions/123e4567-e89b-12d3-a456-426614174000")
    assert "app-001" not in route
    assert "123e4567" not in route
    assert len(_fallback_route("/" + "x" * 500)) == 200


def test_metrics_middleware_uses_route_templates_and_exposes_registry() -> None:
    app = FastAPI()
    app.add_middleware(MetricsMiddleware, service_name="shared-test")

    @app.get("/items/{item_id}")
    def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @app.get("/problem")
    def problem() -> None:
        raise HTTPException(status_code=418, detail="test")

    client = TestClient(app)
    assert client.get(f"/items/{uuid.uuid4()}").status_code == 200
    assert client.get("/problem").status_code == 418
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "hedge_http_requests_total" in response.text
    assert 'route="/items/{item_id}"' in response.text
    assert 'status="418"' in response.text


def test_custom_gauge_rendering_is_stable() -> None:
    metrics.set_gauge("queue-depth.test", 3, service="worker-test")
    metrics.set_gauge("queue-depth.test", 4, service="worker-test")
    rendered = metrics.render(service="ignored")
    assert "queue_depth_test" in rendered
    assert 'service="worker-test"' in rendered


def test_logging_and_health_helpers(monkeypatch) -> None:
    from hedge_shared import utils

    monkeypatch.setattr(utils.settings, "LOG_LEVEL", "DEBUG")
    logger = logging.getLogger("shared-helper-test")
    logger.handlers.clear()
    configured = setup_logging("shared-helper-test")
    assert configured.level == logging.DEBUG
    assert len(configured.handlers) == 1
    assert setup_logging("shared-helper-test") is configured
    assert len(configured.handlers) == 1

    basic = create_health_dict("catalogue")
    assert basic["status"] == "ok"
    assert create_health_dict("catalogue", {"postgres": True})["postgres"] is True
    logger.handlers.clear()

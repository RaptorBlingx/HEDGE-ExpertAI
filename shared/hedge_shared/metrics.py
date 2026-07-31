"""Thread-safe, bounded-cardinality Prometheus instrumentation."""

from __future__ import annotations

import re
import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "hedge_http_requests_total",
    "Total HTTP requests",
    ("service", "method", "route", "status"),
    registry=REGISTRY,
)
HTTP_DURATION = Histogram(
    "hedge_http_request_duration_seconds",
    "HTTP request latency",
    ("service", "method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 120, 300),
    registry=REGISTRY,
)
HTTP_ERRORS = Counter(
    "hedge_http_errors_total",
    "Unhandled and HTTP error responses",
    ("service", "method", "route", "status"),
    registry=REGISTRY,
)


def _fallback_route(path: str) -> str:
    """Bound path cardinality when no framework route was resolved."""
    collapsed = re.sub(r"/[0-9a-fA-F-]{8,}", "/{id}", path)
    collapsed = re.sub(r"/app-\d+", "/{app_id}", collapsed)
    return collapsed[:200] or "/"


class _Metrics:
    """Compatibility wrapper for service-specific custom gauges."""

    def __init__(self) -> None:
        self._gauges: dict[str, Gauge] = {}

    def set_gauge(self, name: str, value: float, service: str = "unknown") -> None:
        safe_name = re.sub(r"[^a-zA-Z0-9_:]", "_", name)
        gauge = self._gauges.get(safe_name)
        if gauge is None:
            gauge = Gauge(
                safe_name,
                f"HEDGE runtime gauge {safe_name}",
                ("service",),
                registry=REGISTRY,
            )
            self._gauges[safe_name] = gauge
        gauge.labels(service=service).set(value)

    @staticmethod
    def render(service: str | None = None) -> str:
        del service
        return generate_latest(REGISTRY).decode()


metrics = _Metrics()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Instrument requests and expose the process registry at ``/metrics``."""

    def __init__(self, app: Any, service_name: str = "unknown") -> None:
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path == "/metrics":
            return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

        start = time.monotonic()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.monotonic() - start
            route_object = request.scope.get("route")
            route = getattr(route_object, "path", None) or _fallback_route(request.url.path)
            labels = {
                "service": self.service_name,
                "method": request.method,
                "route": route,
                "status": str(status_code),
            }
            HTTP_REQUESTS.labels(**labels).inc()
            HTTP_DURATION.labels(
                service=self.service_name,
                method=request.method,
                route=route,
            ).observe(duration)
            if status_code >= 400:
                HTTP_ERRORS.labels(**labels).inc()

"""Lightweight Prometheus-compatible metrics (no external dependency).

Exposes counters and histograms at ``/metrics`` in Prometheus text format.
Each service registers a ``MetricsMiddleware`` that captures request count
and latency per endpoint.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


class _Metrics:
    """Thread-safe in-memory metrics store."""

    def __init__(self) -> None:
        self.request_count: dict[str, int] = defaultdict(int)
        self.request_latency_sum: dict[str, float] = defaultdict(float)
        self.request_latency_count: dict[str, int] = defaultdict(int)
        self.error_count: dict[str, int] = defaultdict(int)
        self._custom_gauges: dict[str, float] = {}

    def record_request(self, method: str, path: str, status: int, duration: float) -> None:
        key = f'{method}_{path}_{status}'
        self.request_count[key] += 1
        label = f'{method}_{path}'
        self.request_latency_sum[label] += duration
        self.request_latency_count[label] += 1
        if status >= 400:
            self.error_count[f'{method}_{path}'] += 1

    def set_gauge(self, name: str, value: float) -> None:
        self._custom_gauges[name] = value

    def render(self, service: str) -> str:
        lines: list[str] = []
        lines.append(f"# HELP hedge_http_requests_total Total HTTP requests")
        lines.append(f"# TYPE hedge_http_requests_total counter")
        for key, count in sorted(self.request_count.items()):
            parts = key.rsplit("_", 1)
            method_path, status = parts if len(parts) == 2 else (key, "0")
            lines.append(f'hedge_http_requests_total{{service="{service}",endpoint="{method_path}",status="{status}"}} {count}')

        lines.append(f"# HELP hedge_http_request_duration_seconds Request latency")
        lines.append(f"# TYPE hedge_http_request_duration_seconds summary")
        for key, total in sorted(self.request_latency_sum.items()):
            count = self.request_latency_count.get(key, 1)
            avg = total / count if count else 0
            lines.append(f'hedge_http_request_duration_seconds_sum{{service="{service}",endpoint="{key}"}} {total:.4f}')
            lines.append(f'hedge_http_request_duration_seconds_count{{service="{service}",endpoint="{key}"}} {count}')

        for name, value in sorted(self._custom_gauges.items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f'{name}{{service="{service}"}} {value}')

        return "\n".join(lines) + "\n"


# Singleton per process
metrics = _Metrics()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that instruments every request."""

    def __init__(self, app: Any, service_name: str = "unknown") -> None:
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path == "/metrics":
            return PlainTextResponse(
                metrics.render(self.service_name),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )
        start = time.monotonic()
        response: Response = await call_next(request)
        duration = time.monotonic() - start
        # Normalize path (collapse IDs)
        path = request.url.path.rstrip("/") or "/"
        metrics.record_request(request.method, path, response.status_code, duration)
        return response

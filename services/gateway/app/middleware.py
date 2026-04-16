"""Gateway middleware — CORS, rate limiting, security headers, request ID, API key auth."""

from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Paths that are exempt from API key authentication
_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Optional API key authentication.

    When ``GATEWAY_API_KEY`` is set in the environment, every request that is
    not to a public path must include the key in the ``X-API-Key`` header or
    the ``api_key`` query parameter. When the variable is empty or unset the
    middleware is a pass-through (open access).
    """

    def __init__(self, app):
        super().__init__(app)
        self.api_key: str = os.getenv("GATEWAY_API_KEY", "")

    async def dispatch(self, request: Request, call_next):
        if not self.api_key:
            # Open access — no key configured
            return await call_next(request)

        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if provided != self.api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
            )

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses (OWASP recommended)."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        # HSTS — only effective behind TLS termination (e.g. nginx/traefik)
        if os.getenv("ENABLE_HSTS", "").lower() in ("1", "true", "yes"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a unique request ID for tracing."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Basic in-memory rate limiting: 60 requests/minute per IP."""

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        # Clean old entries
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if now - t < self.window
        ]

        if len(self._requests[client_ip]) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )

        self._requests[client_ip].append(now)
        return await call_next(request)

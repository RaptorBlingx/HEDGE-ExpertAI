"""Gateway middleware — security, tracing, API key auth, JWT auth, rate limiting."""

from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Paths that are exempt from API key authentication
_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}
_TRUTHY = {"1", "true", "yes", "on"}
_JWK_CLIENTS: dict[str, PyJWKClient] = {}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _env_csv(name: str, default: str) -> set[str]:
    raw = os.getenv(name, default)
    return {item.strip() for item in raw.split(",") if item.strip()}


def _get_client_ip(request: Request) -> str:
    if _env_flag("TRUST_PROXY_HEADERS"):
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    client = _JWK_CLIENTS.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url)
        _JWK_CLIENTS[jwks_url] = client
    return client


@dataclass
class AuthenticatedUser:
    sub: str
    roles: list[str]
    scope: str = ""
    preferred_username: str | None = None
    email: str | None = None


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Optional API key authentication.

    When ``GATEWAY_API_KEY`` is set in the environment, every request that is
    not to a public path must include the key in the ``X-API-Key`` header or
    the ``api_key`` query parameter. When the variable is empty or unset the
    middleware is a pass-through (open access).
    """

    async def dispatch(self, request: Request, call_next):
        request.state.api_key_authenticated = False
        api_key = os.getenv("GATEWAY_API_KEY", "")
        auth_header = request.headers.get("Authorization", "")

        if not api_key:
            # Open access — no key configured
            return await call_next(request)

        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # When OAuth is enabled, allow bearer-token auth to proceed without also
        # requiring the legacy API key. JWTAuthMiddleware will validate it.
        if auth_header.lower().startswith("bearer ") and _env_flag("OAUTH_ENABLED"):
            return await call_next(request)

        provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if provided != api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key."},
            )

        request.state.api_key_authenticated = True
        return await call_next(request)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Optional bearer-token parsing and validation.

    Public routes may still be accessed anonymously. When a bearer token is
    provided and OAuth is enabled, it is validated and attached to request state.
    Invalid bearer tokens are rejected early to avoid ambiguous auth behavior.
    """

    async def dispatch(self, request: Request, call_next):
        request.state.user = None

        if not _env_flag("OAUTH_ENABLED"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            return await call_next(request)

        if not auth_header.lower().startswith("bearer "):
            return JSONResponse(status_code=401, content={"detail": "Invalid Authorization header."})

        token = auth_header.split(" ", 1)[1].strip()
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Missing bearer token."})

        try:
            claims = _decode_token(token)
        except (InvalidTokenError, RuntimeError, ValueError) as exc:
            return JSONResponse(status_code=401, content={"detail": f"Invalid bearer token: {exc}"})

        request.state.user = AuthenticatedUser(
            sub=str(claims.get("sub") or claims.get("preferred_username") or "anonymous"),
            roles=sorted(_extract_roles(claims)),
            scope=str(claims.get("scope", "")),
            preferred_username=claims.get("preferred_username"),
            email=claims.get("email"),
        )
        return await call_next(request)


def _decode_token(token: str) -> dict:
    algorithms = [alg.strip() for alg in os.getenv("OAUTH_JWT_ALGORITHMS", "RS256").split(",") if alg.strip()]
    issuer = os.getenv("OAUTH_ISSUER", "").strip() or None
    audience = os.getenv("OAUTH_AUDIENCE", "").strip() or None
    shared_secret = os.getenv("OAUTH_SHARED_SECRET", "").strip()
    jwks_url = os.getenv("OAUTH_JWKS_URL", "").strip()

    options = {"verify_signature": True, "verify_exp": True, "verify_aud": bool(audience), "verify_iss": bool(issuer)}

    if shared_secret:
        key = shared_secret
    elif jwks_url:
        key = _get_jwk_client(jwks_url).get_signing_key_from_jwt(token).key
    else:
        raise RuntimeError("OAuth is enabled but neither OAUTH_SHARED_SECRET nor OAUTH_JWKS_URL is configured")

    kwargs = {"algorithms": algorithms, "options": options}
    if audience:
        kwargs["audience"] = audience
    if issuer:
        kwargs["issuer"] = issuer

    return jwt.decode(token, key, **kwargs)


def _extract_roles(claims: dict) -> set[str]:
    roles: set[str] = set()
    top_level_roles = claims.get("roles")
    if isinstance(top_level_roles, list):
        roles.update(str(role) for role in top_level_roles)

    realm_roles = claims.get("realm_access", {}).get("roles", [])
    if isinstance(realm_roles, list):
        roles.update(str(role) for role in realm_roles)

    client_id = os.getenv("OAUTH_CLIENT_ID", "").strip()
    if client_id:
        client_roles = claims.get("resource_access", {}).get(client_id, {}).get("roles", [])
        if isinstance(client_roles, list):
            roles.update(str(role) for role in client_roles)

    scope = claims.get("scope", "")
    if isinstance(scope, str):
        for item in scope.split():
            if item.startswith("role:"):
                roles.add(item.split(":", 1)[1])

    return roles


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

        client_ip = _get_client_ip(request)
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

"""Gateway middleware — security, tracing, API key auth, JWT auth, rate limiting."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import uuid
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Paths that are exempt from API key authentication
_PUBLIC_PATHS = {"/health", "/live", "/ready", "/docs", "/openapi.json", "/redoc"}
_PUBLIC_PREFIXES = (
    "/api/v1/chat",
    "/api/v1/apps",
    "/api/v1/catalog",
    "/api/v1/feedback",
    "/api/v2/chat",
    "/api/v2/apps",
    "/api/v2/catalog",
    "/api/v2/recommendation-events",
    "/api/v2/sessions",
    "/widget",
)
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
    direct_ip = request.client.host if request.client else "unknown"
    trusted_proxy = False
    if _env_flag("TRUST_PROXY_HEADERS"):
        for network in _env_csv("TRUSTED_PROXY_IPS", "127.0.0.1/32,::1/128"):
            try:
                if ipaddress.ip_address(direct_ip) in ipaddress.ip_network(network, strict=False):
                    trusted_proxy = True
                    break
            except ValueError:
                continue
    if trusted_proxy:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",", 1)[0].strip()
    return direct_ip


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
    not to a public path must include the key in the ``X-API-Key`` header.
    Query-string credentials are deliberately unsupported. When the variable is empty the
    middleware is a pass-through (open access).
    """

    async def dispatch(self, request: Request, call_next):
        request.state.api_key_authenticated = False
        api_key = os.getenv("GATEWAY_API_KEY", "")
        auth_header = request.headers.get("Authorization", "")

        if not api_key:
            # Open access — no key configured
            return await call_next(request)

        if request.url.path in _PUBLIC_PATHS or request.url.path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

        # When OAuth is enabled, allow bearer-token auth to proceed without also
        # requiring the legacy API key. JWTAuthMiddleware will validate it.
        if auth_header.lower().startswith("bearer ") and _env_flag("OAUTH_ENABLED"):
            return await call_next(request)

        provided = request.headers.get("X-API-Key")
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
            "script-src 'self'; "
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
    """Distributed fixed-window limits backed by Valkey."""

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds

    @staticmethod
    def _limit_for_path(path: str, default: int) -> int:
        if path.endswith("/chat") or path.endswith("/chat/stream"):
            return int(os.getenv("RATE_LIMIT_CHAT_PER_MINUTE", "20"))
        if path.endswith("/apps/search"):
            return int(os.getenv("RATE_LIMIT_SEARCH_PER_MINUTE", "60"))
        return int(os.getenv("RATE_LIMIT_DEFAULT_PER_MINUTE", str(default)))

    @staticmethod
    def _bucket(path: str) -> str:
        if path.endswith("/chat") or path.endswith("/chat/stream"):
            return "chat"
        if path.endswith("/apps/search"):
            return "search"
        return "default"

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in {"/health", "/live", "/ready"}:
            return await call_next(request)

        client_ip = _get_client_ip(request)
        user = getattr(request.state, "user", None)
        identity = getattr(user, "sub", None) or client_ip
        identity_hash = hashlib.sha256(str(identity).encode()).hexdigest()[:24]
        limit = self._limit_for_path(request.url.path, self.max_requests)
        key = f"hedge:ratelimit:{self._bucket(request.url.path)}:{identity_hash}"
        try:
            import redis.asyncio as redis_async

            client = redis_async.from_url(
                os.getenv("VALKEY_RATE_LIMIT_URL", "redis://valkey-cache:6379/2"),
                decode_responses=True,
            )
            count = await client.eval(
                "local n=redis.call('INCR',KEYS[1]); "
                "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
                1,
                key,
                self.window,
            )
            ttl = await client.ttl(key)
            await client.aclose()
        except Exception:
            if _env_flag("RATE_LIMIT_REQUIRED"):
                return JSONResponse(
                    status_code=503,
                    content={"type": "about:blank", "title": "Rate limiter unavailable", "status": 503},
                )
            return await call_next(request)

        if int(count) > limit:
            return JSONResponse(
                status_code=429,
                content={
                    "type": "about:blank",
                    "title": "Rate limit exceeded",
                    "status": 429,
                    "detail": "Try again after the current window.",
                },
                headers={"Retry-After": str(max(int(ttl), 1))},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(limit - int(count), 0))
        return response

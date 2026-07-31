"""Fail-closed production configuration validation."""

from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on"}
_UNSAFE_VALUES = {"", "change-me", "changeme", "hedge-dev-only", "admin", "password"}


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


def validate_production_environment() -> None:
    """Reject unsafe defaults when ``APP_ENV=production``.

    Local development remains intentionally convenient. Production must make
    its trust boundary, identity provider, distributed limiter, secrets, and
    origins explicit before the gateway can accept traffic.
    """
    if os.getenv("APP_ENV", "development").casefold() != "production":
        return

    errors: list[str] = []
    origins = [item.strip() for item in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")]
    if not origins or "*" in origins or any(not item.startswith("https://") for item in origins):
        errors.append("CORS_ALLOWED_ORIGINS must contain explicit HTTPS origins")
    for flag in ("ENABLE_RBAC", "OAUTH_ENABLED", "RATE_LIMIT_REQUIRED", "ENABLE_HSTS"):
        if not _enabled(flag):
            errors.append(f"{flag} must be true")
    if not os.getenv("OAUTH_ISSUER", "").startswith("https://"):
        errors.append("OAUTH_ISSUER must be an HTTPS URL")
    if not os.getenv("OAUTH_JWKS_URL", "").startswith("https://"):
        errors.append("OAUTH_JWKS_URL must be an HTTPS URL")
    if os.getenv("OAUTH_SHARED_SECRET"):
        errors.append("OAUTH_SHARED_SECRET is not permitted in production")
    for secret_name in ("POSTGRES_PASSWORD",):
        if os.getenv(secret_name, "").strip().casefold() in _UNSAFE_VALUES:
            errors.append(f"{secret_name} must not use a default value")
    if errors:
        joined = "; ".join(errors)
        raise RuntimeError(f"unsafe production configuration: {joined}")

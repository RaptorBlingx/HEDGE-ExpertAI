"""Shared utilities: logging setup and health check helpers."""

from __future__ import annotations

import logging
import sys

from hedge_shared.config import settings


def setup_logging(service_name: str) -> logging.Logger:
    """Configure structured logging for a service."""
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def create_health_dict(service_name: str, extras: dict | None = None) -> dict:
    """Build a standard health-check response dict."""
    result = {
        "status": "ok",
        "service": service_name,
        "version": settings.APP_VERSION,
    }
    if extras:
        result.update(extras)
    return result

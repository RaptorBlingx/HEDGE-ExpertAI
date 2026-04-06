"""App Store API client with adapter pattern."""

from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AppStoreClient(ABC):
    """Base class for App Store API clients."""

    @abstractmethod
    def fetch_all_apps(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def fetch_app(self, app_id: str) -> dict[str, Any] | None:
        ...


class MockApiClient(AppStoreClient):
    """Client for the mock HEDGE-IoT App Store API."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_all_apps(self) -> list[dict[str, Any]]:
        all_apps: list[dict[str, Any]] = []
        page = 1
        page_size = 50
        while True:
            url = f"{self.base_url}/api/apps?page={page}&page_size={page_size}"
            resp = httpx.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            apps = data.get("apps", [])
            all_apps.extend(apps)
            if len(all_apps) >= data.get("total", 0) or not apps:
                break
            page += 1
        logger.info("Fetched %d apps from mock API", len(all_apps))
        return all_apps

    def fetch_app(self, app_id: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/apps/{app_id}"
        resp = httpx.get(url, timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


class HedgeApiClient(AppStoreClient):
    """Client for the real HEDGE-IoT App Store API.

    Placeholder — implement when sandbox access is available.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_all_apps(self) -> list[dict[str, Any]]:
        # TODO: implement when real API spec is available
        raise NotImplementedError("Real HEDGE API client not yet implemented")

    def fetch_app(self, app_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("Real HEDGE API client not yet implemented")


def get_client(mock_url: str, hedge_url: str | None = None) -> AppStoreClient:
    """Factory: return HedgeApiClient if HEDGE_API_URL is set, else MockApiClient."""
    if hedge_url:
        return HedgeApiClient(base_url=hedge_url)
    return MockApiClient(base_url=mock_url)


def compute_checksum(app: dict[str, Any]) -> str:
    """Compute SHA-256 checksum of app metadata for change detection."""
    serialized = json.dumps(app, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()

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

    Expects the sandbox API to follow the same pagination/detail contract as
    the mock service.  The field mapping normalises any naming differences so
    that downstream indexing receives a consistent schema.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _normalise(raw: dict[str, Any]) -> dict[str, Any]:
        """Map HEDGE API field names to the internal schema.

        If the remote payload already uses the expected names the mapping is a
        no-op; otherwise it falls back to common alternatives.
        """
        return {
            "id": raw.get("id") or raw.get("appId", ""),
            "title": raw.get("title") or raw.get("name", ""),
            "description": raw.get("description", ""),
            "tags": raw.get("tags") or raw.get("keywords", []),
            "saref_type": raw.get("saref_type") or raw.get("sarefType", ""),
            "input_datasets": raw.get("input_datasets") or raw.get("inputDatasets", []),
            "output_datasets": raw.get("output_datasets") or raw.get("outputDatasets", []),
            "version": raw.get("version", "1.0.0"),
            "publisher": raw.get("publisher") or raw.get("author", ""),
            "created_at": raw.get("created_at") or raw.get("createdAt"),
            "updated_at": raw.get("updated_at") or raw.get("updatedAt"),
        }

    def fetch_all_apps(self) -> list[dict[str, Any]]:
        all_apps: list[dict[str, Any]] = []
        page = 1
        page_size = 50
        while True:
            url = f"{self.base_url}/api/apps"
            resp = httpx.get(
                url,
                params={"page": page, "page_size": page_size},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            # Accept both {"apps": [...]} and top-level list responses
            apps_raw = data.get("apps") if isinstance(data, dict) else data
            if not apps_raw:
                break
            all_apps.extend(self._normalise(a) for a in apps_raw)

            total = data.get("total", 0) if isinstance(data, dict) else len(apps_raw)
            if len(all_apps) >= total or len(apps_raw) < page_size:
                break
            page += 1

        logger.info("Fetched %d apps from HEDGE API (%s)", len(all_apps), self.base_url)
        return all_apps

    def fetch_app(self, app_id: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/apps/{app_id}"
        resp = httpx.get(url, timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._normalise(resp.json())


def get_client(mock_url: str, hedge_url: str | None = None) -> AppStoreClient:
    """Factory: return HedgeApiClient if HEDGE_API_URL is set, else MockApiClient."""
    if hedge_url:
        return HedgeApiClient(base_url=hedge_url)
    return MockApiClient(base_url=mock_url)


def compute_checksum(app: dict[str, Any]) -> str:
    """Compute SHA-256 checksum of app metadata for change detection."""
    serialized = json.dumps(app, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()

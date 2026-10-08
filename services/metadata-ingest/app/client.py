"""App Store API client with adapter pattern."""

from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx
from hedge_shared.store_v1 import StoreAppMetadata

logger = logging.getLogger(__name__)


def normalize_store_v1_app(raw: object, *, store_id: str | None = None) -> StoreAppMetadata:
    """Normalize one offline Store App; never fetch, infer, or enrich metadata.

    A Store ID from the scoped endpoint may supply an absent fkAppStoreId, but
    a conflicting payload is rejected. Unknown source fields are deliberately
    ignored; malformed known fields fail validation for later quarantine.
    """
    if not isinstance(raw, dict):
        raise ValueError("Store App must be an object")
    native_store = raw.get("fkAppStoreId")
    if store_id is not None and native_store is not None and native_store != store_id:
        raise ValueError("fkAppStoreId conflicts with the requested Store")
    fields = {
        "name": "name",
        "description": "description",
        "provider": "provider",
        "readme": "readme",
        "active": "active",
        "visible": "visible",
        "registrationDate": "registration_date",
        "uiUrl": "ui_url",
        "openAPIURL": "openapi_url",
        "deployURL": "deploy_url",
        "registryBaseURL": "registry_base_url",
    }
    values = {target: raw[source] for source, target in fields.items() if source in raw}
    versions = raw.get("appVersionList")
    if versions is not None:
        if not isinstance(versions, list) or any(not isinstance(v, dict) for v in versions):
            raise ValueError("appVersionList must be an array of objects")
        if any(v.get("fkAppId") is not None and v["fkAppId"] != raw.get("appId") for v in versions):
            raise ValueError("App version belongs to a different App")
        version_fields = {
            "appVersionId": "app_version_id",
            "version": "version",
            "registrationDate": "registration_date",
            "versionComments": "comments",
        }
        values["versions"] = [
            {target: v[source] for source, target in version_fields.items() if source in v}
            for v in versions
        ]
    return StoreAppMetadata(
        store_id=native_store if native_store is not None else store_id,
        app_id=raw.get("appId"),
        **values,
    )


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
        expected_total: int | None = None
        while True:
            url = f"{self.base_url}/api/v2/apps?page={page}&page_size={page_size}"
            resp = httpx.get(url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
                raise ValueError("malformed mock catalogue page")
            total = data.get("total")
            if type(total) is not int or total < 0:
                raise ValueError("missing or invalid mock catalogue total")
            if expected_total is not None and total != expected_total:
                raise ValueError("mock catalogue total changed during pagination")
            expected_total = total
            apps = data["apps"]
            if len(apps) > page_size or len(all_apps) + len(apps) > total:
                raise ValueError("mock catalogue exceeds declared page size or total")
            all_apps.extend(apps)
            if len(all_apps) == total:
                break
            if len(apps) != page_size:
                raise ValueError("incomplete mock catalogue pagination")
            page += 1
        logger.info("Fetched %d apps from mock API", len(all_apps))
        return all_apps

    def fetch_app(self, app_id: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/v2/apps/{app_id}"
        resp = httpx.get(url, timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


class HedgeApiClient(AppStoreClient):
    """Legacy synthetic transport; real Store v1 transport is still pending.

    Offline Store v1 normalization is deliberately separate and not selected
    by this client or the scheduler until safe reconciliation is implemented.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _normalise(raw: dict[str, Any]) -> dict[str, Any]:
        """Accept the versioned fixture contract until the real API is supplied.

        Guessing a field mapping would silently admit incorrect metadata. The
        integration boundary therefore fails explicitly for any unversioned
        shape and can be updated once HEDGE publishes its actual contract.
        """
        if raw.get("schema_version") != "2.0":
            raise ValueError("unsupported HEDGE Store contract; expected schema_version 2.0")
        return raw

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

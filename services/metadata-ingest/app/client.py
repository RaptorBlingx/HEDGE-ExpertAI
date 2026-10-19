"""App Store API client with adapter pattern."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from hedge_shared.config import settings
from hedge_shared.store_auth import StoreAuthError, StoreClientCredentials
from hedge_shared.store_v1 import STORE_APP_FIELDS, NativeIdentifier, StoreAppMetadata
from pydantic import SecretStr, TypeAdapter

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
        **STORE_APP_FIELDS,
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
    def fetch_all_apps(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def fetch_app(self, app_id: str) -> dict[str, Any] | None: ...


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


class StoreApiError(RuntimeError):
    """Sanitized failure: never retain a response body or credential in the message."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _path_identifier(value: str) -> str:
    identifier = TypeAdapter(NativeIdentifier).validate_python(value)
    if identifier in (".", ".."):
        raise ValueError("dot segments cannot be addressed as Store path identifiers")
    return quote(identifier, safe="")


def _reject_json_constant(value: str) -> None:
    raise ValueError("non-finite JSON numbers are not supported")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


class HedgeApiClient(AppStoreClient):
    """Read-only Store v1 transport; never infers catalogue completeness.

    Supports an externally rotated Bearer token or backend client credentials. No browser credentials,
    redirect following, ambient proxies, guessed pagination or asset join.
    """

    snapshot_complete = False
    _NOT_FOUND = object()
    MAX_RESPONSE_BYTES = 10 * 1024 * 1024
    RETRY_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        base_url: str,
        *,
        store_id: str,
        token: str | SecretStr | None = None,
        token_file: str = "",
        credentials: StoreClientCredentials | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ):
        try:
            url = httpx.URL(base_url)
            valid = (
                url.scheme == "https"
                and bool(url.host)
                and not url.userinfo
                and not url.query
                and not url.fragment
                and url.path.rstrip("/").endswith("/api/v1")
            )
        except (httpx.InvalidURL, ValueError):
            valid = False
        if not valid:
            raise ValueError("Store base URL must be credential-free HTTPS ending in /api/v1")
        _path_identifier(store_id)
        if sum((token is not None, bool(token_file), credentials is not None)) != 1:
            raise ValueError("provide exactly one backend token, token file or client credentials")
        if token_file and not Path(token_file).is_absolute():
            raise ValueError("Store token file must use an absolute path")
        if isinstance(timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise ValueError("Store timeout must be greater than zero and at most 120 seconds")
        if type(max_retries) is not int or not 0 <= max_retries <= 3:
            raise ValueError("Store retries must be an integer between zero and three")
        self.base_url = str(url).rstrip("/")
        self.store_id = store_id
        self._token: SecretStr | None = None
        if token is not None:
            self._token = token if isinstance(token, SecretStr) else SecretStr(token)
        self._token_file = token_file
        self._credentials = credentials
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport

    def _bearer_token(self) -> str:
        if self._token is not None:
            token = self._token.get_secret_value()
        else:
            try:
                with Path(self._token_file).open(encoding="utf-8") as handle:
                    content = handle.read(16_386)
            except (OSError, UnicodeError):
                raise StoreApiError("Store backend token file is unavailable") from None
            if len(content) > 16_385:
                raise StoreApiError("Store backend Bearer token is empty or invalid")
            token = content.strip()
        # RFC 6750 b64token syntax; reject header injection and a doubled Bearer prefix.
        if len(token) > 16_384 or not re.fullmatch(r"[A-Za-z0-9._~+/\-]+=*", token):
            raise StoreApiError("Store backend Bearer token is empty or invalid")
        return token

    def _request_json(self, path: str, *, missing_ok: bool = False) -> Any:
        deadline = time.monotonic() + self.timeout
        with httpx.Client(
            timeout=self.timeout,
            verify=True,
            follow_redirects=False,
            trust_env=False,
            transport=self._transport,
        ) as client:
            attempt = 0
            refreshed = False
            while attempt <= self.max_retries:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise StoreApiError("Store API request time budget exhausted")
                retry = False
                try:
                    try:
                        bearer = (self._credentials.token(deadline) if self._credentials
                                  else self._bearer_token())
                    except StoreAuthError as error:
                        raise StoreApiError(str(error), status_code=error.status_code) from None
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise StoreApiError("Store API request time budget exhausted")
                    with client.stream(
                        "GET",
                        self.base_url + path,
                        headers={
                            "Authorization": "Bearer " + bearer,
                            "Accept": "application/json",
                        },
                        timeout=remaining,
                    ) as response:
                        if time.monotonic() >= deadline:
                            raise StoreApiError("Store API request time budget exhausted")
                        status = response.status_code
                        if status == 401 and self._credentials and not refreshed:
                            self._credentials.invalidate(bearer)
                            refreshed = True
                            continue
                        if status in (401, 403):
                            raise StoreApiError(
                                "Store backend authorization rejected", status_code=status
                            )
                        if status == 404 and missing_ok:
                            return self._NOT_FOUND
                        if status in self.RETRY_STATUSES and attempt < self.max_retries:
                            if response.headers.get("retry-after") is not None:
                                # Do not guess a date/delay or retry before the server permits it.
                                raise StoreApiError(
                                    "Store API requested deferred retry", status_code=status
                                )
                            retry = True
                        elif status != 200:
                            raise StoreApiError(
                                "Store API returned an unsuccessful status", status_code=status
                            )
                        else:
                            media_type = (
                                response.headers.get("content-type", "")
                                .split(";", 1)[0]
                                .strip()
                                .lower()
                            )
                            if media_type != "application/json" and not media_type.endswith(
                                "+json"
                            ):
                                raise StoreApiError("Store API response is not JSON")
                            body = bytearray()
                            for chunk in response.iter_bytes():
                                if time.monotonic() >= deadline:
                                    raise StoreApiError("Store API request time budget exhausted")
                                body.extend(chunk)
                                if len(body) > self.MAX_RESPONSE_BYTES:
                                    raise StoreApiError("Store API response exceeds the size limit")
                            try:
                                return json.loads(
                                    body,
                                    parse_constant=_reject_json_constant,
                                    object_pairs_hook=_unique_json_object,
                                )
                            except (ValueError, UnicodeError, RecursionError):
                                raise StoreApiError(
                                    "Store API response contains malformed JSON"
                                ) from None
                except httpx.DecodingError:
                    raise StoreApiError("Store API response decoding failed") from None
                except httpx.TransportError:
                    if attempt == self.max_retries:
                        raise StoreApiError(
                            "Store API transport failed after bounded attempts"
                        ) from None
                    retry = True
                if retry:
                    attempt += 1
                    # Fixed bounded backoff when the server supplied no retry delay.
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise StoreApiError("Store API request time budget exhausted")
                    time.sleep(min(0.25 * 2**(attempt - 1), remaining))
        raise StoreApiError("Store API request failed")

    def fetch_catalogue_records(self) -> list[Any]:
        """Bounded array transport; reconciliation quarantines individual records."""
        data = self._request_json(f"/store/{_path_identifier(self.store_id)}/app/all")
        if not isinstance(data, list):
            raise StoreApiError("Store catalogue response must be an App array")
        return data

    def fetch_all_apps(self) -> list[dict[str, Any]]:
        data = self.fetch_catalogue_records()
        identities: set[str] = set()
        try:
            for raw in data:
                app = normalize_store_v1_app(raw, store_id=self.store_id)
                if app.id in identities:
                    raise ValueError("duplicate identity")
                identities.add(app.id)
        except ValueError:
            raise StoreApiError("Store catalogue contains invalid or duplicate Apps") from None
        return data

    def fetch_app(self, app_id: str) -> dict[str, Any] | None:
        data = self._request_json(
            f"/store/{_path_identifier(self.store_id)}/app/{_path_identifier(app_id)}",
            missing_ok=True,
        )
        if data is self._NOT_FOUND:
            return None
        try:
            app = normalize_store_v1_app(data, store_id=self.store_id)
            if app.app_id != app_id:
                raise ValueError("unexpected App identity")
        except ValueError:
            raise StoreApiError(
                "Store detail response contains an invalid or mismatched App"
            ) from None
        return data

    def fetch_assets(self) -> list[dict[str, Any]]:
        """Retain raw AssetRequest objects; no join/enrichment is established."""
        data = self._request_json("/dsp/connector/asset/all")
        if not isinstance(data, list) or any(not isinstance(asset, dict) for asset in data):
            raise StoreApiError("Store assets response must be an object array")
        return data


def get_client(mock_url: str, hedge_url: str | None = None) -> AppStoreClient:
    """Explicit client factory. The scheduled job remains synthetic-only."""
    if hedge_url:
        return HedgeApiClient(
            base_url=hedge_url,
            store_id=settings.HEDGE_STORE_ID,
            token_file=settings.HEDGE_STORE_TOKEN_FILE,
            credentials=(StoreClientCredentials(settings.HEDGE_STORE_ISSUER,
                         settings.HEDGE_STORE_CLIENT_ID, settings.HEDGE_STORE_CLIENT_SECRET_FILE)
                         if settings.HEDGE_STORE_ISSUER else None),
            timeout=settings.HEDGE_STORE_TIMEOUT_SECONDS,
            max_retries=settings.HEDGE_STORE_MAX_RETRIES,
        )
    return MockApiClient(base_url=mock_url)


def compute_checksum(app: dict[str, Any]) -> str:
    """Compute SHA-256 checksum of app metadata for change detection."""
    serialized = json.dumps(app, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()

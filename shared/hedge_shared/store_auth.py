"""Backend-only OIDC client credentials, cached until shortly before expiry.

No user login/refresh token, ambient proxy, redirect, credential logging or disk
access-token cache. The secret file is reread on renewal for atomic rotation.
"""
from __future__ import annotations

import json
import math
import os
import re
import stat
import threading
import time
from pathlib import Path

import httpx


class StoreAuthError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class StoreClientCredentials:
    MAX_BYTES = 65536

    def __init__(self, issuer: str, client_id: str, secret_file: str, *, transport=None):
        url = httpx.URL(issuer)
        if (url.scheme != "https" or not url.host or url.userinfo or url.query or url.fragment
                or not client_id.strip() or not Path(secret_file).is_absolute()):
            raise ValueError("Store OIDC requires HTTPS issuer, client ID and absolute secret file")
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self._secret_file = secret_file
        self._transport = transport
        self._lock = threading.Lock()
        self._endpoint = None
        self._token = None
        self._expires = 0.0

    def invalidate(self, rejected_token: str) -> None:
        with self._lock:
            if self._token == rejected_token:
                self._token = None
                self._expires = 0.0

    def _secret(self):
        try:
            # O_NOFOLLOW also rejects a symlink swapped between validation and read.
            fd = os.open(self._secret_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "r", encoding="utf-8") as handle:
                info = os.fstat(handle.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o077):
                    raise ValueError
                secret = handle.read(4097).strip()
            if not secret or len(secret) > 4096 or any(ord(c) < 32 for c in secret):
                raise ValueError
            return secret
        except (OSError, ValueError, UnicodeError):
            raise StoreAuthError(
                "Store client secret requires an owned private regular file") from None

    def _json(self, client, method, url, deadline, **kwargs):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StoreAuthError("Store authentication time budget exhausted")
        try:
            with client.stream(method, url, timeout=remaining, **kwargs) as response:
                if response.status_code != 200:
                    raise StoreAuthError("Store client authentication rejected",
                                         status_code=response.status_code)
                media = response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
                if media != "application/json":
                    raise StoreAuthError("Store authentication response is not JSON")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > self.MAX_BYTES or time.monotonic() >= deadline:
                        raise StoreAuthError("Store authentication response exceeded bounds")
                return json.loads(body)
        except (httpx.HTTPError, ValueError, UnicodeError, RecursionError):
            raise StoreAuthError("Store authentication transport or response invalid") from None

    def token(self, deadline: float) -> str:
        if not self._lock.acquire(timeout=max(0, deadline - time.monotonic())):
            raise StoreAuthError("Store authentication time budget exhausted")
        try:
            if self._token and time.monotonic() < self._expires:
                return self._token
            with httpx.Client(verify=True, follow_redirects=False, trust_env=False,
                              transport=self._transport) as client:
                if self._endpoint is None:
                    discovery = self._json(client, "GET", self.issuer +
                                           "/.well-known/openid-configuration", deadline)
                    endpoint = (discovery.get("token_endpoint")
                                if isinstance(discovery, dict) else None)
                    if (not isinstance(endpoint, str) or discovery.get("issuer") != self.issuer):
                        raise StoreAuthError("Store OIDC discovery issuer mismatch")
                    base, target = httpx.URL(self.issuer), httpx.URL(endpoint)
                    # Never send a secret to a different authority advertised in metadata.
                    if (target.scheme != "https" or target.host != base.host
                            or target.port != base.port or target.userinfo
                            or target.query or target.fragment):
                        raise StoreAuthError("Store OIDC token endpoint authority mismatch")
                    self._endpoint = endpoint
                started = time.monotonic()
                data = self._json(client, "POST", self._endpoint, deadline, data={
                    "grant_type": "client_credentials", "client_id": self.client_id,
                    "client_secret": self._secret(),
                })
                if not isinstance(data, dict):
                    raise StoreAuthError("Store token response invalid")
                token, expiry = data.get("access_token"), data.get("expires_in")
                if (not isinstance(token, str) or len(token) > 16384
                        or not re.fullmatch(r"[A-Za-z0-9._~+/\-]+=*", token)
                        or str(data.get("token_type", "")).lower() != "bearer"
                        or type(expiry) not in (int, float) or not math.isfinite(expiry)
                        or expiry <= 0):
                    raise StoreAuthError("Store token response invalid")
                lifetime = min(expiry, 86400)
                self._expires = started + lifetime - min(30, lifetime * .1)
                if time.monotonic() >= self._expires:
                    raise StoreAuthError("Store token already expired")
                self._token = token
                return token
        finally:
            self._lock.release()

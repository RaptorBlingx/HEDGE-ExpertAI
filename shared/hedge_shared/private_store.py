"""Explicit opt-in for an isolated private Store service deployment."""
import hmac
import os
import uuid

from fastapi import Header, HTTPException

from .config import Settings
from .store_v1 import validate_offline_store_scope


def scope() -> dict:
    settings = Settings()
    if not settings.PRIVATE_STORE_ENABLED:
        return {}
    if os.getenv("APP_ENV", "").lower() == "production" or not settings.HEDGE_STORE_ID.strip():
        raise ValueError("Private Store mode requires a Store ID and a non-production environment")
    collection = "hedge_store_offline_" + uuid.uuid5(
        uuid.NAMESPACE_URL, "private-store:" + settings.HEDGE_STORE_ID).hex
    validate_offline_store_scope(settings.HEDGE_STORE_ID, collection)
    return {"store_id": settings.HEDGE_STORE_ID, "collection_name": collection}


def require_internal_key(x_api_key: str = Header(default="")) -> None:
    if not scope():
        raise HTTPException(404, "Private Store mode disabled")
    expected = os.getenv("GATEWAY_API_KEY", "")
    if not expected or not hmac.compare_digest(expected.encode(), x_api_key.encode()):
        raise HTTPException(401, "Invalid internal credential")

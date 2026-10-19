"""Private scheduled synchronization over the existing M2M transport."""
import os
from functools import lru_cache

import httpx
from hedge_shared import store_sync
from hedge_shared.config import Settings
from hedge_shared.private_store import scope

from .client import StoreApiError, get_client
from .snapshot import reconcile_catalogue_snapshot


@lru_cache(maxsize=1)
def client():
    settings = Settings()
    return get_client(mock_url=settings.MOCK_API_URL, hedge_url=settings.HEDGE_API_URL)


def refresh():
    store_id = scope()["store_id"]
    try:
        receipt = reconcile_catalogue_snapshot(
            "private-store-services", client().fetch_catalogue_records,
            store_id=store_id, managed_source="authorized_api")
    except StoreApiError as error:
        store_sync.failed(store_id, error.status_code)
        return {"source_error": "Store access unavailable", "synchronization": store_sync.status(store_id)}
    repair()
    return {"ingestion": receipt, "synchronization": store_sync.status(store_id)}


def repair():
    response = httpx.post(os.environ["DISCOVERY_RANKING_URL"] + "/internal/store/repair",
                          headers={"X-API-Key": os.environ["GATEWAY_API_KEY"]}, json={}, timeout=120)
    response.raise_for_status()
    return response.json()

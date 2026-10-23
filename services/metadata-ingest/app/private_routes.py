"""Private administrative synchronization operations."""
from fastapi import APIRouter, Depends
from hedge_shared import store_sync
from hedge_shared.private_store import require_internal_key, scope

from .private_store import refresh

router = APIRouter(prefix="/internal/store", dependencies=[Depends(require_internal_key)])


@router.get("/status")
def status():
    return {"synchronization": store_sync.status(scope()["store_id"])}


@router.post("/refresh")
def synchronize():
    return refresh()

"""Private HTTP access to the existing Store projection and index reconciler."""
from fastapi import APIRouter, Depends
from hedge_shared import storage, store_sync
from hedge_shared.private_store import require_internal_key, scope
from hedge_shared.store_index import repair_store_index
from hedge_shared.store_knowledge import project
from pydantic import BaseModel, Field

from . import indexer

router = APIRouter(prefix="/internal/store", dependencies=[Depends(require_internal_key)])


class Resolve(BaseModel):
    identities: list[str] | None = Field(default=None, max_length=5000)


@router.post("/catalogue")
def catalogue(req: Resolve):
    store_id = scope()["store_id"]
    identities = req.identities
    if identities is None:
        identities = [row["id"] for row in store_sync.members(store_id) if row["available"]]
    rows = storage.get_catalogue_apps(identities, store_id=store_id)
    return {"apps": [project(rows[i]) for i in identities if i in rows]}


@router.post("/repair")
def repair():
    selected = scope()
    storage.rebuild_store_knowledge(selected["store_id"])
    repair_store_index(selected["store_id"], indexer.get_client(), indexer,
                       selected["collection_name"])
    return {"synchronization": store_sync.status(selected["store_id"])}

"""Source-scoped reconciliation; transport must establish snapshot completeness."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Any

from hedge_shared.models_v2 import AppMetadataV2
from hedge_shared.saref import validate_app_semantics
from hedge_shared.storage import (
    catalogue_snapshot,
    complete_ingestion_run,
    create_ingestion_run,
    quarantine_item,
    tombstone_missing_apps,
    upsert_catalogue_app,
)
from hedge_shared.store_v1 import NativeIdentifier, StoreAppMetadata
from pydantic import TypeAdapter

from .client import normalize_store_v1_app


def reconcile_catalogue_snapshot(
    source: str,
    fetch_apps: Callable[[], list[Any]],
    *,
    snapshot_complete: bool = False,
    store_id: str | None = None,
    allow_empty: bool = False,
    managed_source: str | None = None,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    """Fetch under a source lock, then atomically apply records and safe absence.

    Completeness is explicit, never inferred from a list. Partial/quarantined
    snapshots apply valid records (including publication withdrawal), but cannot
    retire absent Apps. Empty snapshots require deliberate operator approval.
    Store rows remain outside public v2 indexing. Transport is supplied by the callback.
    """
    if managed_source and snapshot_complete:
        raise ValueError("Managed API observations do not establish source completeness")
    if store_id is not None:
        store_id = TypeAdapter(NativeIdentifier).validate_python(store_id)
    run_id = create_ingestion_run(source)
    counts = {"created": 0, "updated": 0, "unchanged": 0, "quarantined": 0}
    fetched = deleted = 0
    try:
        with catalogue_snapshot(source, store_id=store_id) as conn:
            raw_apps = fetch_apps()
            if not isinstance(raw_apps, list):
                raise ValueError("catalogue snapshot must be an array")
            fetched = len(raw_apps)
            accepted: list[tuple[int, AppMetadataV2 | StoreAppMetadata]] = []
            rejected: dict[int, str] = {}
            for position, raw in enumerate(raw_apps):
                try:
                    if store_id is not None:
                        app = normalize_store_v1_app(raw, store_id=store_id)
                    else:
                        app = AppMetadataV2.model_validate(raw)
                        errors = validate_app_semantics(app)
                        if errors:
                            raise ValueError("; ".join(errors))
                    accepted.append((position, app))
                except ValueError as exc:
                    rejected[position] = str(exc)
            identities = Counter(app.id for _, app in accepted)
            for position, app in accepted:
                if identities[app.id] > 1:
                    rejected[position] = "duplicate App identity in snapshot"
                    continue
                try:
                    action = upsert_catalogue_app(
                        run_id,
                        app,
                        source_updated_at=(
                            app.lifecycle.updated_at or app.lifecycle.released_at
                            if isinstance(app, AppMetadataV2)
                            else None
                        ),
                        conn=conn,
                    )
                    counts[action] += 1
                except ValueError as exc:
                    rejected[position] = str(exc)
            for position, error in rejected.items():
                raw = raw_apps[position]
                key = (
                    raw.get("appId" if store_id is not None else "id")
                    if isinstance(raw, dict)
                    else None
                )
                quarantine_item(
                    run_id,
                    source_key=str(key or f"position-{position}"),
                    payload=raw,
                    errors=[error],
                    conn=conn,
                )
            if managed_source:
                if store_id is None:
                    raise ValueError("Managed observations require Store scope")
                from hedge_shared.store_sync import observe

                observe(conn, store_id, {app.id: app.public_eligible for position, app in accepted
                                        if position not in rejected}, run_id, managed_source, captured_at)
            counts["quarantined"] = len(rejected)
            safe_absence = (
                snapshot_complete is True
                and not rejected
                and (bool(raw_apps) or allow_empty is True)
            )
            if safe_absence:
                deleted = tombstone_missing_apps(run_id, conn=conn, store_id=store_id)
            status = "completed" if safe_absence else "partial"
            complete_ingestion_run(
                run_id, status=status, fetched=fetched, deleted=deleted, **counts, conn=conn
            )
    except Exception as exc:
        # The projection, revisions, quarantine and outbox were all rolled back.
        complete_ingestion_run(
            run_id,
            status="failed",
            fetched=fetched,
            created=0,
            updated=0,
            unchanged=0,
            deleted=0,
            quarantined=0,
            error=str(exc),
        )
        raise
    return {"run_id": run_id, "status": status, "fetched": fetched, **counts, "deleted": deleted}

"""Private Store observation state, distinct from authoritative source deletion."""

from datetime import UTC, datetime
from typing import Any

from .storage import connection

# A managed Store's response membership gates both lexical and dense hydration.
# Legacy offline Store projections keep their existing behavior.
AVAILABILITY_SQL = """(
 NOT EXISTS (SELECT 1 FROM store_sync_state s WHERE s.store_id = catalog_apps.source_store_id)
 OR EXISTS (SELECT 1 FROM store_sync_members m
            WHERE m.store_id = catalog_apps.source_store_id AND m.app_id = catalog_apps.id
              AND m.available)
)"""


def observe(
    conn: Any,
    store_id: str,
    available: dict[str, bool],
    run_id: str,
    source_kind: str,
    captured_at: datetime | None = None,
) -> None:
    if source_kind not in {"authorized_api", "authorized_snapshot"}:
        raise ValueError("Unsupported Store observation source")
    now = datetime.now(UTC)
    conn.execute(
        """
        INSERT INTO store_sync_state (store_id, source_kind, snapshot_at,
                                      last_attempt_at, last_success_at, run_id)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (store_id) DO UPDATE SET source_kind=EXCLUDED.source_kind,
          snapshot_at=EXCLUDED.snapshot_at, last_attempt_at=EXCLUDED.last_attempt_at,
          last_success_at=EXCLUDED.last_success_at, last_error=NULL, run_id=EXCLUDED.run_id
    """,
        (
            store_id,
            source_kind,
            captured_at or now,
            now,
            now if source_kind == "authorized_api" else None,
            run_id,
        ),
    )
    # Absence means locally unavailable until positively observed again; retain
    # source payload/history and never infer a complete upstream catalogue.
    conn.execute("UPDATE store_sync_members SET available=false WHERE store_id=%s", (store_id,))
    for identity, eligible in available.items():
        conn.execute(
            """INSERT INTO store_sync_members (store_id, app_id, available)
            VALUES (%s,%s,%s)
            ON CONFLICT (store_id, app_id) DO UPDATE SET available=EXCLUDED.available""",
            (store_id, identity, eligible),
        )


def failed(store_id: str, status: int | None) -> None:
    # Only sanitized transport categories enter durable state, never bodies/tokens.
    reason = "authorization_required" if status in (401, 403) else "source_unavailable"
    with connection() as conn:
        conn.execute(
            """INSERT INTO store_sync_state (store_id, source_kind,
                                                            last_attempt_at, last_error)
            VALUES (%s, 'none', now(), %s) ON CONFLICT (store_id) DO UPDATE
            SET last_attempt_at=now(), last_error=EXCLUDED.last_error""",
            (store_id, reason),
        )


def status(store_id: str) -> dict[str, Any]:
    with connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        row = conn.execute(
            "SELECT * FROM store_sync_state WHERE store_id=%s", (store_id,)
        ).fetchone()
        if row is None:
            return {"state": "not_initialized", "snapshot_complete": False}
        run = (
            conn.execute(
                "SELECT fetched_count, quarantined_count FROM ingestion_runs WHERE id=%s",
                (row["run_id"],),
            ).fetchone()
            if row["run_id"]
            else None
        )
        counts = conn.execute(
            """SELECT count(*) AS known,
            count(*) FILTER (WHERE available) AS available,
            count(*) FILTER (WHERE indexed_revision IS DISTINCT FROM c.revision
              OR indexed_available IS DISTINCT FROM m.available) AS index_pending
            FROM store_sync_members m JOIN catalog_apps c ON c.id=m.app_id WHERE m.store_id=%s""",
            (store_id,),
        ).fetchone()
    basis = (
        "saved_file_mtime" if row["source_kind"] == "authorized_snapshot" else "local_response_time"
    )
    state = "observed_api" if row["source_kind"] == "authorized_api" else "saved_snapshot"
    if run and run["quarantined_count"]:
        state = "partial_observation"
    return {
        **row,
        **counts,
        **(run or {}),
        "snapshot_complete": False,
        "timestamp_basis": basis,
        "state": row["last_error"] or state,
    }


def members(store_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        return conn.execute(
            """SELECT c.id, c.revision, c.payload, m.available
            FROM store_sync_members m JOIN catalog_apps c ON c.id=m.app_id
            WHERE m.store_id=%s ORDER BY c.source_app_id""",
            (store_id,),
        ).fetchall()


def indexed(store_id: str, identity: str, revision: int, available: bool) -> None:
    with connection() as conn:
        conn.execute(
            """UPDATE store_sync_members m SET indexed_revision=%s, indexed_available=%s
            FROM catalog_apps c WHERE m.store_id=%s AND m.app_id=%s AND c.id=m.app_id
            AND c.revision=%s AND m.available=%s""",
            (revision, available, store_id, identity, revision, available),
        )

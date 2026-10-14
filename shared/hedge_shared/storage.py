"""Small PostgreSQL repositories for durable catalogue and KPI state.

The module imports psycopg lazily so pure contract/unit-test users of
``hedge_shared`` do not need an active database or driver.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import datetime
from typing import Any

from .models_v2 import (
    AppMetadataV2,
    RecommendationEventRequest,
    RecommendationEventType,
    SearchFilters,
)
from .store_v1 import StoreAppMetadata


def database_url() -> str:
    """Return the application database DSN."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://hedge:hedge-dev-only@postgres:5432/hedge",
    )


@contextmanager
def connection() -> Iterator[Any]:
    """Yield a transaction-scoped psycopg connection."""
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database_url(), row_factory=dict_row) as conn:
        yield conn


def ping_database() -> bool:
    """Return whether PostgreSQL is reachable."""
    try:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() is not None
    except Exception:
        return False


def create_ingestion_run(source: str) -> str:
    """Create a running ingestion record."""
    run_id = str(uuid.uuid4())
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_runs (id, source, status)
            VALUES (%s, %s, 'running')
            """,
            (run_id, source),
        )
    return run_id


def complete_ingestion_run(
    run_id: str,
    *,
    status: str,
    fetched: int,
    created: int,
    updated: int,
    unchanged: int,
    deleted: int,
    quarantined: int,
    error: str | None = None,
    conn: Any | None = None,
) -> None:
    """Finalize an ingestion record with immutable run statistics."""
    with nullcontext(conn) if conn is not None else connection() as db, db.cursor() as cursor:
        cursor.execute(
            """
            UPDATE ingestion_runs
            SET status = %s,
                completed_at = now(),
                fetched_count = %s,
                created_count = %s,
                updated_count = %s,
                unchanged_count = %s,
                deleted_count = %s,
                quarantined_count = %s,
                error = %s
            WHERE id = %s
            """,
            (
                status,
                fetched,
                created,
                updated,
                unchanged,
                deleted,
                quarantined,
                error,
                run_id,
            ),
        )


def latest_ingestion_run() -> dict[str, Any] | None:
    """Return the most recently started ingestion run."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, source, status, started_at, completed_at,
                   fetched_count, created_count, updated_count,
                   unchanged_count, deleted_count, quarantined_count, error
            FROM ingestion_runs
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        return cursor.fetchone()


def get_ingestion_run(run_id: str) -> dict[str, Any] | None:
    """Return one durable ingestion run by identifier."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, source, status, started_at, completed_at,
                   fetched_count, created_count, updated_count,
                   unchanged_count, deleted_count, quarantined_count, error
            FROM ingestion_runs WHERE id = %s
            """,
            (run_id,),
        )
        return cursor.fetchone()


def list_quarantined_items(
    *,
    run_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    """Page actionable validation failures for an administrative client."""
    where = "WHERE status = 'quarantined'"
    params: list[Any] = []
    if run_id:
        where += " AND ingestion_run_id = %s"
        params.append(run_id)
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(f"SELECT count(*) AS total FROM ingestion_items {where}", params)
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            f"""
            SELECT id, ingestion_run_id, source_key, validation_errors, created_at
            FROM ingestion_items {where}
            ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
            """,
            [*params, limit, offset],
        )
        return total, cursor.fetchall()


def _lock_catalogue_source(cursor: Any, *, source: str, store_id: str | None) -> None:
    # Store identity, rather than transport URL, defines the synchronization scope.
    scope = ["hedge-store-v1", store_id] if store_id is not None else ["2.0", source]
    cursor.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (json.dumps(scope, ensure_ascii=False),),
    )


@contextmanager
def catalogue_snapshot(source: str, *, store_id: str | None = None) -> Iterator[Any]:
    """Serialize a source from BEFORE fetch through atomic reconciliation.

    Fetch inside this context: locking only the writes lets a delayed older
    fetch overwrite newer publication state. Different Stores use distinct locks.
    """
    with connection() as conn, conn.cursor() as cursor:
        _lock_catalogue_source(cursor, source=source, store_id=store_id)
        yield conn


def upsert_catalogue_app(
    run_id: str,
    app: AppMetadataV2 | StoreAppMetadata,
    *,
    source_updated_at: datetime | None = None,
    conn: Any | None = None,
) -> str:
    """Upsert one app and enqueue its vector revision in the same transaction.

    Store source profiles are retained offline without v2 indexing operations.
    Returns ``created``, ``updated``, or ``unchanged``.
    """
    store_app = isinstance(app, StoreAppMetadata)
    # Store derived values are recomputed on read, not accepted as source facts.
    excluded = {"checksum", "id", "public_eligible"} if store_app else {"checksum"}
    payload = app.model_dump(mode="json", exclude=excluded)
    search_document = app.to_index_text("en")
    checksum = app.checksum
    if store_app and source_updated_at is not None:
        raise ValueError("Store v1 has no confirmed source update timestamp")
    schema_version = app.source_profile if store_app else app.schema_version
    active = app.public_eligible if store_app else True
    native_store = app.store_id if store_app else None
    native_app = app.app_id if store_app else None
    with nullcontext(conn) if conn is not None else connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT source FROM ingestion_runs WHERE id = %s", (run_id,))
        run = cursor.fetchone()
        if run is None:
            raise ValueError("unknown ingestion run")
        _lock_catalogue_source(cursor, source=run["source"], store_id=native_store)
        cursor.execute(
            """
            SELECT checksum, revision, schema_version, active, last_seen_run_id
            FROM catalog_apps WHERE id = %s FOR UPDATE
            """,
            (app.id,),
        )
        existing = cursor.fetchone()
        if existing and existing["schema_version"] != schema_version:
            raise ValueError("catalogue key belongs to a different source profile")
        if existing and not store_app and existing["last_seen_run_id"] is not None:
            # Read ownership AFTER locking the row; a concurrent first claim
            # may have changed last_seen_run_id while this statement waited.
            cursor.execute(
                "SELECT source FROM ingestion_runs WHERE id = %s", (existing["last_seen_run_id"],)
            )
            if cursor.fetchone()["source"] != run["source"]:
                raise ValueError("catalogue key belongs to a different source")
        if existing and existing["checksum"] == checksum and existing["active"] == active:
            cursor.execute(
                """
                UPDATE catalog_apps
                SET active = %s,
                    last_seen_run_id = %s,
                    search_document = %s,
                    source_updated_at = COALESCE(%s, source_updated_at)
                WHERE id = %s
                """,
                (active, run_id, search_document, source_updated_at, app.id),
            )
            return "unchanged"

        revision = int(existing["revision"]) + 1 if existing else 1
        action = "updated" if existing else "created"
        cursor.execute(
            """
            INSERT INTO catalog_apps (
                id, checksum, revision, schema_version, payload, search_document,
                active, source_updated_at, last_seen_run_id, searchable_at,
                source_store_id, source_app_id
            )
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, NULL, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                checksum = EXCLUDED.checksum,
                revision = EXCLUDED.revision,
                payload = EXCLUDED.payload,
                search_document = EXCLUDED.search_document,
                active = EXCLUDED.active,
                source_store_id = EXCLUDED.source_store_id,
                source_app_id = EXCLUDED.source_app_id,
                source_updated_at = EXCLUDED.source_updated_at,
                last_seen_run_id = EXCLUDED.last_seen_run_id,
                searchable_at = NULL,
                updated_at = now()
            """,
            (
                app.id,
                checksum,
                revision,
                schema_version,
                json.dumps(payload),
                search_document,
                active,
                source_updated_at,
                run_id,
                native_store,
                native_app,
            ),
        )
        cursor.execute(
            """
            INSERT INTO catalog_app_revisions (
                app_id, revision, checksum, payload, ingestion_run_id
            )
            VALUES (%s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (app_id, revision) DO NOTHING
            """,
            (app.id, revision, checksum, json.dumps(payload), run_id),
        )
        if not store_app:
            cursor.execute(
                """
                INSERT INTO indexing_outbox (app_id, revision, operation, payload, status)
                VALUES (%s, %s, 'upsert', %s::jsonb, 'pending')
                ON CONFLICT (app_id, revision, operation) DO NOTHING
                """,
                (app.id, revision, json.dumps(payload)),
            )
        return action


def quarantine_item(
    run_id: str,
    *,
    source_key: str,
    payload: Any,
    errors: list[dict[str, Any]] | list[str],
    conn: Any | None = None,
) -> None:
    """Persist an invalid source record without admitting it to the catalogue."""
    with nullcontext(conn) if conn is not None else connection() as db, db.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_items (
                ingestion_run_id, source_key, status, payload, validation_errors
            )
            VALUES (%s, %s, 'quarantined', %s::jsonb, %s::jsonb)
            """,
            (run_id, source_key, json.dumps(payload), json.dumps(errors)),
        )


def tombstone_missing_apps(run_id: str, *, conn: Any, store_id: str | None = None) -> int:
    """Retire absent Apps in a validated snapshot's transaction and source scope.

    Only call after complete, unquarantined, nonempty (or explicitly approved
    empty) validation inside catalogue_snapshot. Source facts stay unchanged.
    """
    if store_id is not None:
        scope = "schema_version = 'hedge-store-v1' AND source_store_id = %s"
        scope_params = (store_id,)
    else:
        scope = """schema_version = '2.0' AND last_seen_run_id IN (
            SELECT id FROM ingestion_runs WHERE source = (
                SELECT source FROM ingestion_runs WHERE id = %s
            )
        )"""
        scope_params = (run_id,)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE catalog_apps
            SET active = false, revision = revision + 1, updated_at = now(), searchable_at = NULL
            WHERE active = true AND last_seen_run_id IS DISTINCT FROM %s AND {scope}
            RETURNING id, revision, checksum, payload
            """,
            (run_id, *scope_params),
        )
        rows = cursor.fetchall()
        for row in rows:
            cursor.execute(
                """
                INSERT INTO catalog_app_revisions
                    (app_id, revision, checksum, payload, ingestion_run_id)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                """,
                (row["id"], row["revision"], row["checksum"], json.dumps(row["payload"]), run_id),
            )
            if store_id is None:
                cursor.execute(
                    """
                    INSERT INTO indexing_outbox (app_id, revision, operation, payload, status)
                    VALUES (%s, %s, 'delete', '{}'::jsonb, 'pending')
                    ON CONFLICT (app_id, revision, operation) DO NOTHING
                    """,
                    (row["id"], row["revision"]),
                )
        return len(rows)


OUTBOX_MAX_ATTEMPTS = 10
OUTBOX_LEASE_SECONDS = 180


def pending_outbox(limit: int = 100) -> list[dict[str, Any]]:
    """Claim due operations, including abandoned leases; retain exhausted work."""
    with connection() as conn, conn.cursor() as cursor:
        # A crash on the final attempt must become visible terminal failure too.
        cursor.execute(
            """
            UPDATE indexing_outbox SET status = 'failed', next_attempt_at = NULL,
                last_error = 'Index delivery interrupted on final attempt', updated_at = now()
            WHERE status = 'processing' AND attempts >= %s
              AND updated_at < now() - make_interval(secs => %s)
            """,
            (OUTBOX_MAX_ATTEMPTS, OUTBOX_LEASE_SECONDS),
        )
        cursor.execute(
            """
            WITH claimed AS (
                SELECT id FROM indexing_outbox
                WHERE attempts < %s AND (
                    (status IN ('pending', 'failed')
                     AND (next_attempt_at IS NULL OR next_attempt_at <= now()))
                    OR (status = 'processing'
                        AND updated_at < now() - make_interval(secs => %s))
                )
                ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT %s
            )
            UPDATE indexing_outbox AS outbox
            SET status = 'processing', attempts = attempts + 1, updated_at = clock_timestamp()
            FROM claimed WHERE outbox.id = claimed.id
            RETURNING outbox.id, outbox.app_id, outbox.revision, outbox.operation,
                      outbox.payload, outbox.attempts, outbox.updated_at
            """,
            (OUTBOX_MAX_ATTEMPTS, OUTBOX_LEASE_SECONDS, limit),
        )
        return cursor.fetchall()


def complete_outbox_item(
    outbox_id: int, *, app_id: str, revision: int, claimed_at: datetime
) -> bool:
    """Acknowledge only this claim; a late worker cannot complete a new lease."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE indexing_outbox
            SET status = 'completed', completed_at = now(), updated_at = now(),
                last_error = NULL, next_attempt_at = NULL
            WHERE id = %s AND app_id = %s AND revision = %s
              AND status = 'processing' AND updated_at = %s
            RETURNING operation
            """,
            (outbox_id, app_id, revision, claimed_at),
        )
        item = cursor.fetchone()
        if item is None:
            return False
        if item["operation"] == "upsert":
            cursor.execute(
                """
                UPDATE catalog_apps SET searchable_at = now()
                WHERE id = %s AND revision = %s AND active = true AND schema_version = '2.0'
                """,
                (app_id, revision),
            )
        return True


def fail_outbox_item(outbox_id: int, error: str, *, claimed_at: datetime) -> bool:
    """Fence failure acknowledgements and retain terminal failures for explicit replay."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE indexing_outbox SET status = 'failed', last_error = left(%s, 2000),
                next_attempt_at = CASE WHEN attempts >= %s THEN NULL ELSE
                    now() + make_interval(secs => LEAST(3600, power(2, attempts)::int)) END,
                updated_at = now()
            WHERE id = %s AND status = 'processing' AND updated_at = %s
            RETURNING id
            """,
            (error, OUTBOX_MAX_ATTEMPTS, outbox_id, claimed_at),
        )
        return cursor.fetchone() is not None


def outbox_status() -> dict[str, int]:
    """Expose durable backlog and exhausted work independently of ingestion runs."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*) FILTER (WHERE status != 'completed') AS outstanding,
                   count(*) FILTER (WHERE status = 'failed' AND attempts >= %s) AS exhausted
            FROM indexing_outbox
            """,
            (OUTBOX_MAX_ATTEMPTS,),
        )
        return dict(cursor.fetchone())


def retry_outbox_item(outbox_id: int) -> bool:
    """Explicitly release one exhausted operation after its underlying fault is fixed."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE indexing_outbox SET status = 'pending', attempts = 0,
                next_attempt_at = NULL, updated_at = clock_timestamp()
            WHERE id = %s AND status = 'failed' AND attempts >= %s RETURNING id
            """,
            (outbox_id, OUTBOX_MAX_ATTEMPTS),
        )
        return cursor.fetchone() is not None


@contextmanager
def catalogue_index_app(app_id: str) -> Iterator[dict[str, Any] | None]:
    """Serialize a vector write with catalogue updates and other writers of this App."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute(
            "SELECT id, revision, active, schema_version, checksum, payload "
            "FROM catalog_apps WHERE id = %s FOR UPDATE",
            (app_id,),
        )
        yield cursor.fetchone()


def get_catalogue_apps(
    app_ids: list[str], *, store_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve eligible candidates; synthetic by default, with optional native Store scope."""
    if not app_ids:
        return {}
    scope = "schema_version = '2.0'"
    params: list[Any] = [app_ids]
    if store_id is not None:
        scope = (
            "schema_version = 'hedge-store-v1' AND source_store_id = %s "
            "AND payload->'active' = 'true'::jsonb AND payload->'visible' = 'true'::jsonb"
        )
        params.append(store_id)
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT id, revision, payload FROM catalog_apps "
            f"WHERE id = ANY(%s) AND active = true AND {scope}",
            params,
        )
        return {row["id"]: row for row in cursor.fetchall()}


def lexical_search(
    query: str,
    *,
    locale: str,
    filters: SearchFilters,
    limit: int,
    store_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return an independent PostgreSQL full-text candidate ranking."""
    # The simple dictionary is deliberate: it is deterministic across all
    # eight locales and the catalogue also stores curated localized keywords.
    where = ["active = true", "schema_version = '2.0'"]
    filter_params: list[Any] = []

    if filters.publisher:
        where.append("payload #>> '{publisher,name}' ILIKE %s")
        filter_params.append(f"%{filters.publisher}%")
    if filters.lifecycle_status:
        where.append("payload #>> '{lifecycle,status}' = %s")
        filter_params.append(filters.lifecycle_status.value)
    if filters.license_spdx:
        where.append("payload #>> '{trust,license_spdx}' = %s")
        filter_params.append(filters.license_spdx)
    if filters.tags:
        where.append("payload->'tags' ?& %s")
        filter_params.append(filters.tags)
    if filters.capabilities:
        where.append("payload->'capabilities' ?& %s")
        filter_params.append(filters.capabilities)
    if filters.protocols:
        where.append("payload->'protocols' ?& %s")
        filter_params.append(filters.protocols)
    if filters.supported_languages:
        where.append("payload->'supported_languages' ?& %s")
        filter_params.append([str(value) for value in filters.supported_languages])
    if filters.semantic_uri:
        where.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements(payload->'semantic_annotations') a "
            "WHERE a->>'term_uri' = %s)"
        )
        filter_params.append(str(filters.semantic_uri))
    if filters.extension_uri:
        where.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements(payload->'semantic_annotations') a "
            "WHERE a->>'ontology_uri' = %s)"
        )
        filter_params.append(str(filters.extension_uri))
    if filters.deployment_modes:
        where.append("payload #> '{deployment,modes}' ?| %s")
        filter_params.append(filters.deployment_modes)
    if filters.data_classifications:
        where.append(
            "EXISTS (SELECT 1 FROM jsonb_array_elements("
            "COALESCE(payload->'inputs', '[]'::jsonb) || COALESCE(payload->'outputs', '[]'::jsonb)"
            ") d WHERE d->>'data_classification' = ANY(%s))"
        )
        filter_params.append(filters.data_classifications)

    document = "search_document"
    if store_id is not None:
        # No supported taxonomy/language/license assertions exist in Store Apps.
        if any(value for key, value in filters.model_dump().items() if key != "publisher"):
            return []
        where = [
            "active = true", "schema_version = 'hedge-store-v1'", "source_store_id = %s",
            "payload->'active' = 'true'::jsonb", "payload->'visible' = 'true'::jsonb",
        ]
        filter_params = [store_id]
        if filters.publisher:
            where.append("payload->>'provider' ILIKE %s")
            filter_params.append(f"%{filters.publisher}%")
        # Ingestion derives this document with the shared Store evidence extractor.
        # Reingesting also refreshes legacy documents when source values are unchanged.

    del locale  # Reserved for future language-specific PostgreSQL dictionaries.
    sql = f"""
        SELECT id, revision, payload,
               ts_rank_cd(
                   to_tsvector('simple', {document}),
                   websearch_to_tsquery('simple', %s),
                   32
               ) AS lexical_score
        FROM catalog_apps
        WHERE {" AND ".join(where)}
          AND to_tsvector('simple', {document})
              @@ websearch_to_tsquery('simple', %s)
        ORDER BY lexical_score DESC, id
        LIMIT %s
    """
    params = [query, *filter_params, query, limit]
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def get_catalogue_app(app_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
    """Read the authoritative current catalogue payload."""
    clause = "" if include_inactive else "AND active = true"
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"SELECT payload FROM catalog_apps WHERE id = %s AND schema_version = '2.0' {clause}",
            (app_id,),
        )
        row = cursor.fetchone()
        return row["payload"] if row else None


def list_catalogue_apps(*, limit: int, offset: int = 0) -> tuple[int, list[dict[str, Any]]]:
    """List active catalogue apps from the durable source of truth."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) AS total FROM catalog_apps "
            "WHERE active = true AND schema_version = '2.0'"
        )
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT payload
            FROM catalog_apps
            WHERE active = true AND schema_version = '2.0'
            ORDER BY id
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        return total, [row["payload"] for row in cursor.fetchall()]


def current_catalogue_revision() -> str:
    """Return a deterministic cache namespace for the active catalogue state."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(md5(string_agg(id || ':' || revision::text, ',' ORDER BY id)), 'empty')
                   AS revision
            FROM catalog_apps WHERE active = true AND schema_version = '2.0'
            """
        )
        return str(cursor.fetchone()["revision"])


def create_impression(
    *,
    session_id: str,
    result_ids: list[str],
    locale: str,
    intent: str,
    request_id: str | None = None,
    timings: dict[str, float] | None = None,
) -> str:
    """Persist a pseudonymous recommendation impression without message text."""
    impression_id = f"imp-{uuid.uuid4()}"
    session_hash = hashlib.sha256(session_id.encode()).hexdigest()
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO recommendation_impressions (
                id, session_hash, request_id, locale, intent, result_ids, timings
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            """,
            (
                impression_id,
                session_hash,
                request_id,
                locale,
                intent,
                json.dumps(result_ids),
                json.dumps(timings or {}),
            ),
        )
    return impression_id


def record_recommendation_event(event: RecommendationEventRequest) -> bool:
    """Validate an impression/app pair and insert an idempotent KPI event.

    Returns ``False`` when the idempotency key was already recorded.
    """
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT result_ids FROM recommendation_impressions WHERE id = %s",
            (event.impression_id,),
        )
        impression = cursor.fetchone()
        if impression is None:
            raise LookupError("impression not found")
        if (
            event.event_type == RecommendationEventType.APP_OPENED
            and event.app_id not in impression["result_ids"]
        ):
            raise ValueError("app was not part of the impression")

        cursor.execute(
            """
            INSERT INTO recommendation_events (
                impression_id, idempotency_key, event_type, app_id, occurred_at
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING id
            """,
            (
                event.impression_id,
                event.idempotency_key,
                event.event_type.value,
                event.app_id,
                event.occurred_at,
            ),
        )
        return cursor.fetchone() is not None


def recommendation_kpis() -> dict[str, Any]:
    """Compute session-level acceptance and qualified app-open counts."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            WITH session_outcomes AS (
                SELECT
                    impressions.session_hash,
                    bool_or(events.event_type = 'recommendation_accepted') AS accepted,
                    bool_or(events.event_type = 'recommendation_dismissed') AS dismissed
                FROM recommendation_impressions AS impressions
                JOIN recommendation_events AS events
                  ON events.impression_id = impressions.id
                WHERE events.event_type IN (
                    'recommendation_accepted',
                    'recommendation_dismissed'
                )
                GROUP BY impressions.session_hash
            ), event_counts AS (
                SELECT count(*) FILTER (WHERE event_type = 'app_opened') AS app_opened
                FROM recommendation_events
            )
            SELECT
                count(*) FILTER (WHERE accepted) AS accepted,
                count(*) FILTER (WHERE NOT accepted AND dismissed) AS dismissed,
                (SELECT app_opened FROM event_counts) AS app_opened
            FROM session_outcomes
            """
        )
        row = cursor.fetchone()
        accepted = int(row["accepted"] or 0)
        dismissed = int(row["dismissed"] or 0)
        denominator = accepted + dismissed
        return {
            "accepted_sessions": accepted,
            "dismissed_sessions": dismissed,
            "qualified_app_opens": int(row["app_opened"] or 0),
            "acceptance_rate": round(accepted / denominator, 4) if denominator else None,
            "raw_event_window_days": 30,
        }


def apply_data_retention(*, as_of: datetime | None = None) -> dict[str, int]:
    """Aggregate expired KPI events and remove expired event/transcript rows.

    The aggregation and deletions share one PostgreSQL transaction, so a failed
    run cannot double-count data on retry. Session hashes and app identifiers are
    deliberately absent from the retained aggregate table.
    """
    cutoff = as_of or datetime.now().astimezone()
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO recommendation_daily_aggregates (
                day, locale, intent, event_type, event_count, distinct_sessions
            )
            SELECT
                events.occurred_at::date,
                impressions.locale,
                impressions.intent,
                events.event_type,
                count(*),
                count(DISTINCT impressions.session_hash)
            FROM recommendation_impressions AS impressions
            JOIN recommendation_events AS events
              ON events.impression_id = impressions.id
            WHERE impressions.expires_at <= %s
            GROUP BY
                events.occurred_at::date,
                impressions.locale,
                impressions.intent,
                events.event_type
            ON CONFLICT (day, locale, intent, event_type) DO UPDATE
            SET event_count = recommendation_daily_aggregates.event_count
                    + EXCLUDED.event_count,
                distinct_sessions = recommendation_daily_aggregates.distinct_sessions
                    + EXCLUDED.distinct_sessions,
                updated_at = now()
            """,
            (cutoff,),
        )
        aggregate_groups = max(cursor.rowcount, 0)

        cursor.execute(
            "DELETE FROM recommendation_impressions WHERE expires_at <= %s",
            (cutoff,),
        )
        expired_impressions = max(cursor.rowcount, 0)

        cursor.execute(
            "DELETE FROM consented_transcripts WHERE expires_at <= %s",
            (cutoff,),
        )
        expired_transcripts = max(cursor.rowcount, 0)

    return {
        "aggregate_groups": aggregate_groups,
        "expired_impressions": expired_impressions,
        "expired_transcripts": expired_transcripts,
    }

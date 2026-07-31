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
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from .models_v2 import (
    AppMetadataV2,
    RecommendationEventRequest,
    RecommendationEventType,
    SearchFilters,
)


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
) -> None:
    """Finalize an ingestion record with immutable run statistics."""
    with connection() as conn, conn.cursor() as cursor:
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


def upsert_catalogue_app(
    run_id: str,
    app: AppMetadataV2,
    *,
    source_updated_at: datetime | None = None,
) -> str:
    """Upsert one app and enqueue its vector revision in the same transaction.

    Returns ``created``, ``updated``, or ``unchanged``.
    """
    payload = app.model_dump(mode="json", exclude={"checksum"})
    search_document = app.to_index_text("en")
    checksum = app.checksum
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT checksum, revision FROM catalog_apps WHERE id = %s FOR UPDATE",
            (app.id,),
        )
        existing = cursor.fetchone()
        if existing and existing["checksum"] == checksum:
            cursor.execute(
                """
                UPDATE catalog_apps
                SET active = true,
                    last_seen_run_id = %s,
                    source_updated_at = COALESCE(%s, source_updated_at)
                WHERE id = %s
                """,
                (run_id, source_updated_at, app.id),
            )
            return "unchanged"

        revision = int(existing["revision"]) + 1 if existing else 1
        action = "updated" if existing else "created"
        cursor.execute(
            """
            INSERT INTO catalog_apps (
                id, checksum, revision, schema_version, payload, search_document,
                active, source_updated_at, last_seen_run_id, searchable_at
            )
            VALUES (%s, %s, %s, '2.0', %s::jsonb, %s, true, %s, %s, NULL)
            ON CONFLICT (id) DO UPDATE SET
                checksum = EXCLUDED.checksum,
                revision = EXCLUDED.revision,
                payload = EXCLUDED.payload,
                search_document = EXCLUDED.search_document,
                active = true,
                source_updated_at = EXCLUDED.source_updated_at,
                last_seen_run_id = EXCLUDED.last_seen_run_id,
                searchable_at = NULL,
                updated_at = now()
            """,
            (
                app.id,
                checksum,
                revision,
                json.dumps(payload),
                search_document,
                source_updated_at,
                run_id,
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
    payload: dict[str, Any],
    errors: list[dict[str, Any]] | list[str],
) -> None:
    """Persist an invalid source record without admitting it to the catalogue."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO ingestion_items (
                ingestion_run_id, source_key, status, payload, validation_errors
            )
            VALUES (%s, %s, 'quarantined', %s::jsonb, %s::jsonb)
            """,
            (run_id, source_key, json.dumps(payload), json.dumps(errors)),
        )


def tombstone_missing_apps(run_id: str) -> int:
    """Deactivate apps not observed in a complete source snapshot."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE catalog_apps
            SET active = false, revision = revision + 1, updated_at = now(), searchable_at = NULL
            WHERE active = true AND last_seen_run_id IS DISTINCT FROM %s
            RETURNING id, revision
            """,
            (run_id,),
        )
        rows = cursor.fetchall()
        for row in rows:
            cursor.execute(
                """
                INSERT INTO indexing_outbox (app_id, revision, operation, payload, status)
                VALUES (%s, %s, 'delete', '{}'::jsonb, 'pending')
                ON CONFLICT (app_id, revision, operation) DO NOTHING
                """,
                (row["id"], row["revision"]),
            )
        return len(rows)


def pending_outbox(limit: int = 100) -> list[dict[str, Any]]:
    """Claim pending/failed index operations for replay-safe delivery."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            WITH claimed AS (
                SELECT id
                FROM indexing_outbox
                WHERE status IN ('pending', 'failed')
                  AND attempts < 10
                  AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE indexing_outbox AS outbox
            SET status = 'processing', attempts = attempts + 1, updated_at = now()
            FROM claimed
            WHERE outbox.id = claimed.id
            RETURNING outbox.id, outbox.app_id, outbox.revision,
                      outbox.operation, outbox.payload, outbox.attempts
            """,
            (limit,),
        )
        return cursor.fetchall()


def complete_outbox_item(outbox_id: int, *, app_id: str, revision: int) -> None:
    """Mark a delivered vector revision searchable."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE indexing_outbox
            SET status = 'completed', completed_at = now(), updated_at = now(), last_error = NULL
            WHERE id = %s
            """,
            (outbox_id,),
        )
        cursor.execute(
            """
            UPDATE catalog_apps
            SET searchable_at = now()
            WHERE id = %s AND revision = %s AND active = true
            """,
            (app_id, revision),
        )


def fail_outbox_item(outbox_id: int, error: str) -> None:
    """Retain a failed operation for exponential retry."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE indexing_outbox
            SET status = 'failed',
                last_error = left(%s, 2000),
                next_attempt_at = now() + make_interval(
                    secs => LEAST(3600, power(2, attempts)::int)
                ),
                updated_at = now()
            WHERE id = %s
            """,
            (error, outbox_id),
        )


def lexical_search(
    query: str,
    *,
    locale: str,
    filters: SearchFilters,
    limit: int,
) -> list[dict[str, Any]]:
    """Return an independent PostgreSQL full-text candidate ranking."""
    # The simple dictionary is deliberate: it is deterministic across all
    # eight locales and the catalogue also stores curated localized keywords.
    where = ["active = true", "searchable_at IS NOT NULL"]
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

    del locale  # Reserved for future language-specific PostgreSQL dictionaries.
    sql = f"""
        SELECT id, revision, payload,
               ts_rank_cd(
                   to_tsvector('simple', search_document),
                   websearch_to_tsquery('simple', %s),
                   32
               ) AS lexical_score
        FROM catalog_apps
        WHERE {" AND ".join(where)}
          AND to_tsvector('simple', search_document)
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
            f"SELECT payload FROM catalog_apps WHERE id = %s {clause}",
            (app_id,),
        )
        row = cursor.fetchone()
        return row["payload"] if row else None


def list_catalogue_apps(*, limit: int, offset: int = 0) -> tuple[int, list[dict[str, Any]]]:
    """List active catalogue apps from the durable source of truth."""
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT count(*) AS total FROM catalog_apps WHERE active = true")
        total = int(cursor.fetchone()["total"])
        cursor.execute(
            """
            SELECT payload
            FROM catalog_apps
            WHERE active = true
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
            FROM catalog_apps WHERE active = true
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

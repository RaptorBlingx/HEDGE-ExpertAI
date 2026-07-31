CREATE TABLE IF NOT EXISTS schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id uuid PRIMARY KEY,
    source text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'partial')),
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    fetched_count integer NOT NULL DEFAULT 0,
    created_count integer NOT NULL DEFAULT 0,
    updated_count integer NOT NULL DEFAULT 0,
    unchanged_count integer NOT NULL DEFAULT 0,
    deleted_count integer NOT NULL DEFAULT 0,
    quarantined_count integer NOT NULL DEFAULT 0,
    error text
);

CREATE TABLE IF NOT EXISTS ingestion_items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ingestion_run_id uuid NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
    source_key text NOT NULL,
    status text NOT NULL CHECK (status IN ('accepted', 'quarantined')),
    payload jsonb NOT NULL,
    validation_errors jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog_apps (
    id text PRIMARY KEY,
    checksum char(64) NOT NULL,
    revision bigint NOT NULL,
    schema_version text NOT NULL,
    payload jsonb NOT NULL,
    search_document text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    source_updated_at timestamptz,
    searchable_at timestamptz,
    last_seen_run_id uuid REFERENCES ingestion_runs(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog_app_revisions (
    app_id text NOT NULL,
    revision bigint NOT NULL,
    checksum char(64) NOT NULL,
    payload jsonb NOT NULL,
    ingestion_run_id uuid REFERENCES ingestion_runs(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (app_id, revision)
);

CREATE TABLE IF NOT EXISTS indexing_outbox (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_id text NOT NULL,
    revision bigint NOT NULL,
    operation text NOT NULL CHECK (operation IN ('upsert', 'delete')),
    payload jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (app_id, revision, operation)
);

CREATE TABLE IF NOT EXISTS corpus_sources (
    id text PRIMARY KEY,
    title text NOT NULL,
    source_url text NOT NULL,
    license_spdx text NOT NULL,
    source_revision text NOT NULL,
    content_sha256 char(64) NOT NULL,
    retrieved_at timestamptz NOT NULL,
    chunking_version text NOT NULL,
    approved boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS recommendation_impressions (
    id text PRIMARY KEY,
    session_hash char(64) NOT NULL,
    request_id text,
    locale text NOT NULL,
    intent text NOT NULL,
    result_ids jsonb NOT NULL,
    timings jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '30 days'
);

CREATE TABLE IF NOT EXISTS recommendation_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    impression_id text NOT NULL REFERENCES recommendation_impressions(id) ON DELETE CASCADE,
    idempotency_key text NOT NULL UNIQUE,
    event_type text NOT NULL CHECK (
        event_type IN ('recommendation_accepted', 'recommendation_dismissed', 'app_opened')
    ),
    app_id text,
    occurred_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (event_type = 'app_opened' AND app_id IS NOT NULL)
        OR (event_type <> 'app_opened' AND app_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS consented_transcripts (
    id uuid PRIMARY KEY,
    consent_reference text NOT NULL,
    session_hash char(64) NOT NULL,
    encrypted_payload bytea NOT NULL,
    encryption_key_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    deleted_at timestamptz
);

CREATE INDEX IF NOT EXISTS catalog_apps_search_idx
    ON catalog_apps USING gin (to_tsvector('simple', search_document));
CREATE INDEX IF NOT EXISTS catalog_apps_payload_idx
    ON catalog_apps USING gin (payload jsonb_path_ops);
CREATE INDEX IF NOT EXISTS indexing_outbox_pending_idx
    ON indexing_outbox (status, next_attempt_at, created_at);
CREATE INDEX IF NOT EXISTS recommendation_impressions_session_idx
    ON recommendation_impressions (session_hash, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS recommendation_events_response_once_idx
    ON recommendation_events (impression_id)
    WHERE event_type IN ('recommendation_accepted', 'recommendation_dismissed');

INSERT INTO schema_migrations (version)
VALUES ('0001_initial')
ON CONFLICT (version) DO NOTHING;

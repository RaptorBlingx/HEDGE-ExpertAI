-- Private managed Store synchronization; no public indexing policy is enabled.
CREATE TABLE store_sync_state (
    store_id text PRIMARY KEY,
    source_kind text NOT NULL,
    snapshot_at timestamptz,
    last_attempt_at timestamptz,
    last_success_at timestamptz,
    last_error text,
    run_id text
);
CREATE TABLE store_sync_members (
    store_id text NOT NULL REFERENCES store_sync_state(store_id),
    app_id text NOT NULL REFERENCES catalog_apps(id),
    available boolean NOT NULL,
    indexed_revision bigint,
    indexed_available boolean,
    PRIMARY KEY (store_id, app_id)
);

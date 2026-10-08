-- Additive: existing synthetic keys, payloads, revisions and outbox are untouched.
ALTER TABLE catalog_apps
    ADD COLUMN source_store_id text,
    ADD COLUMN source_app_id text,
    ADD CONSTRAINT catalog_apps_store_identity_check CHECK (
        (schema_version = 'hedge-store-v1'
            AND source_store_id IS NOT NULL AND length(btrim(source_store_id)) > 0
            AND source_app_id IS NOT NULL AND length(btrim(source_app_id)) > 0)
        OR (schema_version <> 'hedge-store-v1'
            AND source_store_id IS NULL AND source_app_id IS NULL)
    );

CREATE UNIQUE INDEX catalog_apps_store_identity_idx
    ON catalog_apps (source_store_id, source_app_id)
    WHERE schema_version = 'hedge-store-v1';

INSERT INTO schema_migrations (version)
VALUES ('0003_store_identity')
ON CONFLICT (version) DO NOTHING;

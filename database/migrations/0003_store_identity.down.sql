-- Refuse rollback when it would discard native identity. Export/migrate source
-- rows before attempting this downgrade; never rewrite them as synthetic v2.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM catalog_apps WHERE schema_version = 'hedge-store-v1') THEN
        RAISE EXCEPTION 'Store source rows exist; preserve them before downgrade';
    END IF;
END $$;

DROP INDEX catalog_apps_store_identity_idx;
ALTER TABLE catalog_apps
    DROP CONSTRAINT catalog_apps_store_identity_check,
    DROP COLUMN source_store_id,
    DROP COLUMN source_app_id;
DELETE FROM schema_migrations WHERE version = '0003_store_identity';

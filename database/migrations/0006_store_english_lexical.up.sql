-- Add a rebuildable English sparse index; preserve the existing simple index.
-- No source payloads, identities, revisions or vector embeddings change.
CREATE INDEX catalog_apps_store_english_search_idx
    ON catalog_apps USING gin (to_tsvector('english', search_document))
    WHERE active = true AND schema_version = 'hedge-store-v1';

-- Rebuildable source-derived knowledge, never part of the authoritative payload.
ALTER TABLE catalog_apps ADD COLUMN prepared_knowledge jsonb;

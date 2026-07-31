DROP INDEX IF EXISTS consented_transcripts_expiry_idx;
DROP INDEX IF EXISTS recommendation_impressions_expiry_idx;
DROP TABLE IF EXISTS recommendation_daily_aggregates;
DELETE FROM schema_migrations WHERE version = '0002_retention_aggregates';

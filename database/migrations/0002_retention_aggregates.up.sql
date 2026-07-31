CREATE TABLE IF NOT EXISTS recommendation_daily_aggregates (
    day date NOT NULL,
    locale text NOT NULL,
    intent text NOT NULL,
    event_type text NOT NULL CHECK (
        event_type IN ('recommendation_accepted', 'recommendation_dismissed', 'app_opened')
    ),
    event_count bigint NOT NULL CHECK (event_count >= 0),
    distinct_sessions bigint NOT NULL CHECK (distinct_sessions >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (day, locale, intent, event_type)
);

CREATE INDEX IF NOT EXISTS recommendation_impressions_expiry_idx
    ON recommendation_impressions (expires_at);
CREATE INDEX IF NOT EXISTS consented_transcripts_expiry_idx
    ON consented_transcripts (expires_at)
    WHERE deleted_at IS NULL;

INSERT INTO schema_migrations (version)
VALUES ('0002_retention_aggregates')
ON CONFLICT (version) DO NOTHING;

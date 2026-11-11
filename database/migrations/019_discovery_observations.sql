-- Apply before updating the Vault role or enabling observation ingestion.
CREATE TABLE IF NOT EXISTS discovery_observations (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id) ON DELETE CASCADE,
    source VARCHAR(100) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_sha256 VARCHAR(64) NOT NULL
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT uq_discovery_observation_source_time
        UNIQUE (application_id, source, observed_at)
);

COMMENT ON TABLE discovery_observations IS
    'Sanitized observation history. Workloads receive SELECT and INSERT only.';

CREATE TABLE IF NOT EXISTS integration_transfer_events (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,

    destination_scheme VARCHAR(20) NOT NULL,
    destination_host VARCHAR(255) NOT NULL,
    destination_trust VARCHAR(50) NOT NULL,

    declared_classification VARCHAR(50) NOT NULL,
    effective_sensitivity VARCHAR(50),

    decision VARCHAR(20) NOT NULL,
    allowed BOOLEAN NOT NULL,
    reasons JSONB NOT NULL,

    dlp_sensitive_data_detected BOOLEAN NOT NULL,
    dlp_finding_count INTEGER NOT NULL,
    dlp_highest_sensitivity VARCHAR(50),
    dlp_detected_types JSONB NOT NULL,

    gateway_version VARCHAR(100) NOT NULL,
    dlp_engine_version VARCHAR(100) NOT NULL,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transfer_events_application_id
    ON integration_transfer_events(application_id);

CREATE INDEX IF NOT EXISTS idx_transfer_events_evaluated_at
    ON integration_transfer_events(evaluated_at);

CREATE INDEX IF NOT EXISTS idx_transfer_events_decision
    ON integration_transfer_events(decision);

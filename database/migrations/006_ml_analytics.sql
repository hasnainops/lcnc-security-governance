ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS connector_count INTEGER,
    ADD COLUMN IF NOT EXISTS external_integration_count INTEGER,
    ADD COLUMN IF NOT EXISTS unapproved_integration_count INTEGER,
    ADD COLUMN IF NOT EXISTS external_domain_count INTEGER,
    ADD COLUMN IF NOT EXISTS changes_last_24h INTEGER,
    ADD COLUMN IF NOT EXISTS ml_anomaly_status VARCHAR(30) DEFAULT 'not_assessed',
    ADD COLUMN IF NOT EXISTS ml_anomalous BOOLEAN,
    ADD COLUMN IF NOT EXISTS ml_decision_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ml_model_version VARCHAR(100),
    ADD COLUMN IF NOT EXISTS ml_assessed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS ml_assessments (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    analysis_type VARCHAR(100) NOT NULL,
    anomalous BOOLEAN NOT NULL,
    decision_score DOUBLE PRECISION NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    features JSONB NOT NULL,
    context_signals JSONB NOT NULL DEFAULT '[]'::jsonb,
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ml_assessments_application_id
    ON ml_assessments(application_id);

CREATE INDEX IF NOT EXISTS idx_ml_assessments_assessed_at
    ON ml_assessments(assessed_at);

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS risk_level VARCHAR(50),
    ADD COLUMN IF NOT EXISTS risk_model_version VARCHAR(100),
    ADD COLUMN IF NOT EXISTS risk_assessed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS risk_assessments (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    level VARCHAR(50) NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    factors JSONB NOT NULL DEFAULT '[]'::jsonb,
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_assessments_application_id
    ON risk_assessments(application_id);

CREATE INDEX IF NOT EXISTS idx_risk_assessments_assessed_at
    ON risk_assessments(assessed_at);

CREATE TABLE IF NOT EXISTS dynamic_compliance_assessments (
    id UUID PRIMARY KEY,

    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,

    assessment_version VARCHAR(100) NOT NULL,
    overall_status VARCHAR(30) NOT NULL,

    summary JSONB NOT NULL,
    controls JSONB NOT NULL,

    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dynamic_compliance_application_id
    ON dynamic_compliance_assessments(application_id);

CREATE INDEX IF NOT EXISTS idx_dynamic_compliance_assessed_at
    ON dynamic_compliance_assessments(assessed_at);

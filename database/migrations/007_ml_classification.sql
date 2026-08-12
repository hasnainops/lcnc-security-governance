ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS data_fields TEXT,
    ADD COLUMN IF NOT EXISTS connector_metadata TEXT,
    ADD COLUMN IF NOT EXISTS ml_classification_status VARCHAR(30) DEFAULT 'not_assessed',
    ADD COLUMN IF NOT EXISTS ml_suggested_classification VARCHAR(50),
    ADD COLUMN IF NOT EXISTS ml_classification_confidence DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ml_classification_review_required BOOLEAN,
    ADD COLUMN IF NOT EXISTS ml_classification_model_version VARCHAR(100),
    ADD COLUMN IF NOT EXISTS ml_classified_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS classification_assessments (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    suggested_classification VARCHAR(50) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    review_required BOOLEAN NOT NULL,
    review_threshold DOUBLE PRECISION NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    class_probabilities JSONB NOT NULL,
    inputs JSONB NOT NULL,
    authority VARCHAR(30) NOT NULL DEFAULT 'advisory',
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_classification_assessments_application_id
    ON classification_assessments(application_id);

CREATE INDEX IF NOT EXISTS idx_classification_assessments_classified_at
    ON classification_assessments(classified_at);

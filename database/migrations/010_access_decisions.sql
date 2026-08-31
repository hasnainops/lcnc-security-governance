CREATE TABLE IF NOT EXISTS access_decisions (
    id UUID PRIMARY KEY,

    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,

    subject_id VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    requested_action VARCHAR(50) NOT NULL,

    allowed BOOLEAN NOT NULL,
    decision VARCHAR(20) NOT NULL,
    reasons JSONB NOT NULL,

    registration_status VARCHAR(50) NOT NULL,
    data_classification VARCHAR(50) NOT NULL,

    policy_version VARCHAR(100) NOT NULL,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_access_decisions_application_id
    ON access_decisions(application_id);

CREATE INDEX IF NOT EXISTS idx_access_decisions_subject_id
    ON access_decisions(subject_id);

CREATE INDEX IF NOT EXISTS idx_access_decisions_evaluated_at
    ON access_decisions(evaluated_at);

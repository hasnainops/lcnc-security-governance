ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS governance_status VARCHAR(50)
        NOT NULL DEFAULT 'not_evaluated',
    ADD COLUMN IF NOT EXISTS governance_outcome VARCHAR(50),
    ADD COLUMN IF NOT EXISTS governance_decided_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS governance_decisions (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    risk_assessment_id UUID
        REFERENCES risk_assessments(id)
        ON DELETE SET NULL,
    policy_decision_id UUID
        REFERENCES policy_decisions(id)
        ON DELETE SET NULL,
    outcome VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    required_role VARCHAR(100),
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_governance_decisions_application_id
    ON governance_decisions(application_id);

CREATE INDEX IF NOT EXISTS idx_governance_decisions_created_at
    ON governance_decisions(created_at);

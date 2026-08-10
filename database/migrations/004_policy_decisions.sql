CREATE TABLE IF NOT EXISTS policy_decisions (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    allowed BOOLEAN NOT NULL,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_version VARCHAR(100) NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_policy_decisions_application_id
    ON policy_decisions(application_id);

CREATE INDEX IF NOT EXISTS idx_policy_decisions_evaluated_at
    ON policy_decisions(evaluated_at);

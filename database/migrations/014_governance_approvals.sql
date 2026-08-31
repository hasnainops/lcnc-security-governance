CREATE TABLE IF NOT EXISTS approval_requests (
    id UUID PRIMARY KEY,

    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,

    governance_decision_id UUID NOT NULL
        REFERENCES governance_decisions(id)
        ON DELETE CASCADE,

    route_type VARCHAR(50) NOT NULL,

    status VARCHAR(50) NOT NULL
        DEFAULT 'pending',

    required_role VARCHAR(100) NOT NULL,

    assigned_to VARCHAR(255),

    risk_level VARCHAR(50),

    governance_outcome VARCHAR(50) NOT NULL,

    due_at TIMESTAMPTZ NOT NULL,

    escalation_level INTEGER NOT NULL
        DEFAULT 0,

    escalated_at TIMESTAMPTZ,

    human_decision VARCHAR(50),

    decided_by VARCHAR(255),

    decision_reason TEXT,

    decided_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    UNIQUE (
        governance_decision_id
    )
);


CREATE INDEX IF NOT EXISTS idx_approval_requests_application_id
ON approval_requests(application_id);


CREATE INDEX IF NOT EXISTS idx_approval_requests_status
ON approval_requests(status);


CREATE INDEX IF NOT EXISTS idx_approval_requests_due_at
ON approval_requests(due_at);


CREATE TABLE IF NOT EXISTS approval_events (
    id UUID PRIMARY KEY,

    approval_request_id UUID NOT NULL
        REFERENCES approval_requests(id)
        ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,

    actor VARCHAR(255),

    details JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_approval_events_request_id
ON approval_events(approval_request_id);


CREATE INDEX IF NOT EXISTS idx_approval_events_created_at
ON approval_events(created_at);

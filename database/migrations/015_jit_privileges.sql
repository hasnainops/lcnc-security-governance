BEGIN;

CREATE TABLE IF NOT EXISTS privilege_requests (
    id UUID PRIMARY KEY,

    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,

    subject_id VARCHAR(255) NOT NULL,

    base_role VARCHAR(50) NOT NULL,

    requested_action VARCHAR(50) NOT NULL,

    justification TEXT NOT NULL,

    status VARCHAR(50) NOT NULL
        DEFAULT 'pending',

    required_role VARCHAR(100) NOT NULL
        DEFAULT 'Security/GRC Reviewer',

    requested_duration_minutes INTEGER NOT NULL,

    requested_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    decided_by VARCHAR(255),

    decision_reason TEXT,

    decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_privilege_requests_application_id
ON privilege_requests(application_id);

CREATE INDEX IF NOT EXISTS idx_privilege_requests_subject_id
ON privilege_requests(subject_id);

CREATE INDEX IF NOT EXISTS idx_privilege_requests_status
ON privilege_requests(status);


CREATE TABLE IF NOT EXISTS privilege_grants (
    id UUID PRIMARY KEY,

    privilege_request_id UUID NOT NULL UNIQUE
        REFERENCES privilege_requests(id)
        ON DELETE CASCADE,

    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,

    subject_id VARCHAR(255) NOT NULL,

    granted_action VARCHAR(50) NOT NULL,

    granted_by VARCHAR(255) NOT NULL,

    status VARCHAR(50) NOT NULL
        DEFAULT 'active',

    granted_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    expires_at TIMESTAMPTZ NOT NULL,

    revoked_at TIMESTAMPTZ,

    revoked_by VARCHAR(255),

    revocation_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_privilege_grants_application_id
ON privilege_grants(application_id);

CREATE INDEX IF NOT EXISTS idx_privilege_grants_subject_id
ON privilege_grants(subject_id);

CREATE INDEX IF NOT EXISTS idx_privilege_grants_status
ON privilege_grants(status);

CREATE INDEX IF NOT EXISTS idx_privilege_grants_expires_at
ON privilege_grants(expires_at);


CREATE TABLE IF NOT EXISTS privilege_events (
    id UUID PRIMARY KEY,

    privilege_request_id UUID
        REFERENCES privilege_requests(id)
        ON DELETE CASCADE,

    privilege_grant_id UUID
        REFERENCES privilege_grants(id)
        ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,

    actor VARCHAR(255),

    details JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_privilege_events_request_id
ON privilege_events(privilege_request_id);

CREATE INDEX IF NOT EXISTS idx_privilege_events_grant_id
ON privilege_events(privilege_grant_id);

CREATE INDEX IF NOT EXISTS idx_privilege_events_created_at
ON privilege_events(created_at);

COMMIT;

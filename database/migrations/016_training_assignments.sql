BEGIN;

CREATE TABLE IF NOT EXISTS training_assignments (
    id UUID PRIMARY KEY,

    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,

    subject_id VARCHAR(255),

    module_id VARCHAR(100) NOT NULL,

    trigger_control VARCHAR(50) NOT NULL,

    trigger_status VARCHAR(50) NOT NULL,

    trigger_reason TEXT,

    status VARCHAR(50) NOT NULL
        DEFAULT 'assigned',

    required BOOLEAN NOT NULL
        DEFAULT TRUE,

    assigned_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    due_at TIMESTAMPTZ NOT NULL,

    completed_at TIMESTAMPTZ,

    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    UNIQUE (
        application_id,
        module_id
    )
);

CREATE INDEX IF NOT EXISTS idx_training_assignments_application_id
ON training_assignments(application_id);

CREATE INDEX IF NOT EXISTS idx_training_assignments_subject_id
ON training_assignments(subject_id);

CREATE INDEX IF NOT EXISTS idx_training_assignments_status
ON training_assignments(status);

CREATE INDEX IF NOT EXISTS idx_training_assignments_due_at
ON training_assignments(due_at);


CREATE TABLE IF NOT EXISTS training_events (
    id UUID PRIMARY KEY,

    training_assignment_id UUID NOT NULL
        REFERENCES training_assignments(id)
        ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,

    actor VARCHAR(255),

    details JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_training_events_assignment_id
ON training_events(training_assignment_id);

CREATE INDEX IF NOT EXISTS idx_training_events_created_at
ON training_events(created_at);

COMMIT;

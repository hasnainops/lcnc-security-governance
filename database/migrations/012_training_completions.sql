CREATE TABLE IF NOT EXISTS training_completions (
    id UUID PRIMARY KEY,

    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,

    subject_id VARCHAR(255) NOT NULL,
    module_id VARCHAR(100) NOT NULL,

    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        application_id,
        subject_id,
        module_id
    )
);

CREATE INDEX IF NOT EXISTS idx_training_completions_application_id
    ON training_completions(application_id);

CREATE INDEX IF NOT EXISTS idx_training_completions_subject_id
    ON training_completions(subject_id);

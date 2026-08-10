CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE NOT NULL,

    name VARCHAR(255) NOT NULL,
    platform VARCHAR(100) NOT NULL,

    owner_name VARCHAR(255),
    owner_email VARCHAR(255),
    business_unit VARCHAR(255),
    business_purpose TEXT,

    registration_status VARCHAR(50) NOT NULL DEFAULT 'unregistered',
    lifecycle_status VARCHAR(50) NOT NULL DEFAULT 'active',

    data_classification VARCHAR(50) NOT NULL DEFAULT 'unknown',

    internet_exposed BOOLEAN NOT NULL DEFAULT FALSE,
    external_integration BOOLEAN,
    integration_approved BOOLEAN,

    credential_type VARCHAR(100),

    risk_status VARCHAR(50) NOT NULL DEFAULT 'not_assessed',
    risk_score INTEGER,
    risk_level VARCHAR(50),
    risk_model_version VARCHAR(100),
    risk_assessed_at TIMESTAMPTZ,

    first_discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

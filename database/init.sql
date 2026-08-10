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

    first_discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

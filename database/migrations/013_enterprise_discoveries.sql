CREATE TABLE IF NOT EXISTS enterprise_discoveries (
    discovery_id UUID PRIMARY KEY,

    source VARCHAR(100) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    platform VARCHAR(100) NOT NULL,

    authorization_status VARCHAR(50) NOT NULL DEFAULT 'unknown',

    owner_known BOOLEAN,
    business_purpose_known BOOLEAN,
    internet_exposed BOOLEAN,
    uses_api_key BOOLEAN,

    external_integration_count INTEGER,
    unapproved_integration_count INTEGER,
    connector_count INTEGER,
    external_domain_count INTEGER,
    changes_last_24h INTEGER,

    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,

    handoff_status VARCHAR(50) NOT NULL,
    ml_status VARCHAR(50),
    ml_result JSONB,

    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        source,
        external_id
    )
);

CREATE INDEX IF NOT EXISTS idx_enterprise_discoveries_source
ON enterprise_discoveries(source);

CREATE INDEX IF NOT EXISTS idx_enterprise_discoveries_platform
ON enterprise_discoveries(platform);

CREATE INDEX IF NOT EXISTS idx_enterprise_discoveries_authorization_status
ON enterprise_discoveries(authorization_status);

CREATE INDEX IF NOT EXISTS idx_enterprise_discoveries_handoff_status
ON enterprise_discoveries(handoff_status);

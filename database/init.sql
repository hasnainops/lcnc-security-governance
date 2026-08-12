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
    governance_status VARCHAR(50) NOT NULL DEFAULT 'not_evaluated',
    governance_outcome VARCHAR(50),
    governance_decided_at TIMESTAMPTZ,

    connector_count INTEGER,
    external_integration_count INTEGER,
    unapproved_integration_count INTEGER,
    external_domain_count INTEGER,
    changes_last_24h INTEGER,

    ml_anomaly_status VARCHAR(30) NOT NULL DEFAULT 'not_assessed',
    ml_anomalous BOOLEAN,
    ml_decision_score DOUBLE PRECISION,
    ml_model_version VARCHAR(100),
    ml_assessed_at TIMESTAMPTZ,

    data_fields TEXT,
    connector_metadata TEXT,

    ml_classification_status VARCHAR(30) NOT NULL DEFAULT 'not_assessed',
    ml_suggested_classification VARCHAR(50),
    ml_classification_confidence DOUBLE PRECISION,
    ml_classification_review_required BOOLEAN,
    ml_classification_model_version VARCHAR(100),
    ml_classified_at TIMESTAMPTZ,

    security_scan_status VARCHAR(30) NOT NULL DEFAULT 'not_scanned',
    security_finding_count INTEGER,
    security_highest_severity VARCHAR(30),
    security_scan_passed BOOLEAN,
    security_scanner_version VARCHAR(100),
    security_scanned_at TIMESTAMPTZ,

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


CREATE TABLE IF NOT EXISTS classification_assessments (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    suggested_classification VARCHAR(50) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    review_required BOOLEAN NOT NULL,
    review_threshold DOUBLE PRECISION NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    class_probabilities JSONB NOT NULL,
    inputs JSONB NOT NULL,
    authority VARCHAR(30) NOT NULL DEFAULT 'advisory',
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_classification_assessments_application_id
    ON classification_assessments(application_id);

CREATE INDEX IF NOT EXISTS idx_classification_assessments_classified_at
    ON classification_assessments(classified_at);


CREATE TABLE IF NOT EXISTS security_scans (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    scanner_version VARCHAR(100) NOT NULL,
    finding_count INTEGER NOT NULL,
    highest_severity VARCHAR(30),
    passed BOOLEAN NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS security_findings (
    id UUID PRIMARY KEY,
    scan_id UUID NOT NULL
        REFERENCES security_scans(id)
        ON DELETE CASCADE,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    rule_id VARCHAR(30) NOT NULL,
    title VARCHAR(255) NOT NULL,
    severity VARCHAR(30) NOT NULL,
    evidence TEXT NOT NULL,
    remediation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_scans_application_id
    ON security_scans(application_id);

CREATE INDEX IF NOT EXISTS idx_security_findings_application_id
    ON security_findings(application_id);

CREATE INDEX IF NOT EXISTS idx_security_findings_scan_id
    ON security_findings(scan_id);


CREATE TABLE IF NOT EXISTS integration_transfer_events (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    destination_scheme VARCHAR(20) NOT NULL,
    destination_host VARCHAR(255) NOT NULL,
    destination_trust VARCHAR(50) NOT NULL,
    declared_classification VARCHAR(50) NOT NULL,
    effective_sensitivity VARCHAR(50),
    decision VARCHAR(20) NOT NULL,
    allowed BOOLEAN NOT NULL,
    reasons JSONB NOT NULL,
    dlp_sensitive_data_detected BOOLEAN NOT NULL,
    dlp_finding_count INTEGER NOT NULL,
    dlp_highest_sensitivity VARCHAR(50),
    dlp_detected_types JSONB NOT NULL,
    gateway_version VARCHAR(100) NOT NULL,
    dlp_engine_version VARCHAR(100) NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transfer_events_application_id
    ON integration_transfer_events(application_id);

CREATE INDEX IF NOT EXISTS idx_transfer_events_evaluated_at
    ON integration_transfer_events(evaluated_at);

CREATE INDEX IF NOT EXISTS idx_transfer_events_decision
    ON integration_transfer_events(decision);


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


CREATE TABLE IF NOT EXISTS dynamic_compliance_assessments (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL
        REFERENCES applications(id)
        ON DELETE CASCADE,
    assessment_version VARCHAR(100) NOT NULL,
    overall_status VARCHAR(30) NOT NULL,
    summary JSONB NOT NULL,
    controls JSONB NOT NULL,
    assessed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dynamic_compliance_application_id
    ON dynamic_compliance_assessments(application_id);

CREATE INDEX IF NOT EXISTS idx_dynamic_compliance_assessed_at
    ON dynamic_compliance_assessments(assessed_at);


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

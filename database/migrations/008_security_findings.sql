ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS security_scan_status VARCHAR(30) DEFAULT 'not_scanned',
    ADD COLUMN IF NOT EXISTS security_finding_count INTEGER,
    ADD COLUMN IF NOT EXISTS security_highest_severity VARCHAR(30),
    ADD COLUMN IF NOT EXISTS security_scan_passed BOOLEAN,
    ADD COLUMN IF NOT EXISTS security_scanner_version VARCHAR(100),
    ADD COLUMN IF NOT EXISTS security_scanned_at TIMESTAMPTZ;

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

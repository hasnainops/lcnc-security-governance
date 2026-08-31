ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS workflow_security_metadata JSONB;

COMMENT ON COLUMN applications.workflow_security_metadata IS
    'Sanitized workflow security evidence observed by trusted platform discovery.';

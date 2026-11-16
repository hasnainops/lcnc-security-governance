-- CR-002: authenticated owner declarations and automatic advisory classification.
-- Additive; existing evidence and authoritative classifications are retained.
BEGIN;

CREATE TABLE IF NOT EXISTS application_owner_credentials (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    token_sha256 CHAR(64) NOT NULL UNIQUE,
    subject_id VARCHAR(255) NOT NULL,
    owner_name VARCHAR(255) NOT NULL,
    owner_email VARCHAR(255) NOT NULL,
    issued_by VARCHAR(255) NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (expires_at > issued_at)
);

CREATE TABLE IF NOT EXISTS application_owner_contexts (
    id UUID PRIMARY KEY,
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    credential_id UUID NOT NULL REFERENCES application_owner_credentials(id),
    subject_id VARCHAR(255) NOT NULL,
    owner_name VARCHAR(255) NOT NULL,
    owner_email VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    payload_sha256 CHAR(64) NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    declared_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (application_id, id)
);
CREATE INDEX IF NOT EXISTS idx_owner_context_application
    ON application_owner_contexts(application_id, declared_at DESC);

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS owner_context_id UUID,
    ADD COLUMN IF NOT EXISTS ml_classification_input_sha256 CHAR(64),
    ADD COLUMN IF NOT EXISTS ml_classification_provenance JSONB,
    ADD COLUMN IF NOT EXISTS ml_classification_pending_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS ml_classification_lease_id UUID,
    ADD COLUMN IF NOT EXISTS ml_classification_lease_until TIMESTAMPTZ;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'applications'::regclass
                     AND conname = 'fk_application_owner_context') THEN
        ALTER TABLE applications ADD CONSTRAINT fk_application_owner_context
            FOREIGN KEY (id, owner_context_id)
            REFERENCES application_owner_contexts(application_id, id);
    END IF;
END $$;

ALTER TABLE classification_assessments
    ADD COLUMN IF NOT EXISTS input_sha256 CHAR(64),
    ADD COLUMN IF NOT EXISTS source_evidence JSONB;

CREATE OR REPLACE FUNCTION invalidate_classification_source()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.name, NEW.business_purpose, NEW.data_fields,
           NEW.connector_metadata, NEW.data_field_evidence, NEW.owner_context_id)
       IS DISTINCT FROM
       ROW(OLD.name, OLD.business_purpose, OLD.data_fields,
           OLD.connector_metadata, OLD.data_field_evidence, OLD.owner_context_id) THEN
        NEW.ml_classification_status := 'stale';
        NEW.ml_suggested_classification := NULL;
        NEW.ml_classification_confidence := NULL;
        NEW.ml_classification_review_required := NULL;
        NEW.ml_classification_model_version := NULL;
        NEW.ml_classified_at := NULL;
        NEW.ml_classification_input_sha256 := NULL;
        NEW.ml_classification_provenance := NULL;
        NEW.ml_classification_pending_reasons := '["source_changed"]'::jsonb;
        NEW.ml_classification_lease_id := NULL;
        NEW.ml_classification_lease_until := NULL;
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_classification_source ON applications;
CREATE TRIGGER trg_classification_source BEFORE UPDATE ON applications
    FOR EACH ROW EXECUTE FUNCTION invalidate_classification_source();

COMMENT ON TABLE application_owner_credentials IS
    'Operator-issued, application-scoped owner-context credentials; only SHA-256 digests of random bearer secrets are stored. Not SSO or reviewer authority.';
COMMENT ON TABLE application_owner_contexts IS
    'Append-only owner declarations authenticated at submission; retained separately from machine observations.';
COMMIT;

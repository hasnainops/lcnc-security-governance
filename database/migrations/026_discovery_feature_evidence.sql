BEGIN;

ALTER TABLE applications
    ADD COLUMN IF NOT EXISTS discovery_feature_evidence JSONB
    CHECK (discovery_feature_evidence IS NULL
           OR jsonb_typeof(discovery_feature_evidence) = 'object');

COMMENT ON COLUMN applications.discovery_feature_evidence IS
    'Server-derived observation, destination policy and feature provenance. '
    'Not caller-supplied approval and not evidence of an executed transfer.';

COMMIT;

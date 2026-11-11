-- LO1: Evidence-backed application field inventory.
-- Machine-observed evidence is separate from owner-declared data_fields.
-- Existing application records remain compatible.

BEGIN;

ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS data_field_evidence JSONB;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'public.applications'::regclass
          AND conname =
              'ck_applications_data_field_evidence_object'
    ) THEN
        ALTER TABLE public.applications
            ADD CONSTRAINT
                ck_applications_data_field_evidence_object
            CHECK (
                data_field_evidence IS NULL
                OR jsonb_typeof(data_field_evidence) = 'object'
            );
    END IF;
END
$migration$;

COMMENT ON COLUMN public.applications.data_field_evidence IS
    'Sanitized Appsmith widget-DSL field evidence, including '
    'inspection coverage, provenance and source observation ID. '
    'Not an authoritative database schema or owner attestation.';

COMMIT;

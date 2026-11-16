BEGIN;
ALTER TABLE public.governance_decisions
    ADD COLUMN IF NOT EXISTS input_sha256 VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_evidence JSONB;
COMMENT ON COLUMN public.governance_decisions.input_sha256 IS
    'Automatic governance semantic input fingerprint; NULL for historical/manual decisions.';
COMMIT;

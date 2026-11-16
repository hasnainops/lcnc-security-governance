-- LO2: Distinguish gateway evaluation from controlled-egress enforcement.
-- Historical evaluation-only events retain NULL enforcement fields.
-- No historical enforcement results are fabricated.

BEGIN;

ALTER TABLE public.integration_transfer_events
    ADD COLUMN IF NOT EXISTS enforcement_outcome VARCHAR(32),
    ADD COLUMN IF NOT EXISTS enforced_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS upstream_status_code INTEGER;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid =
            'public.integration_transfer_events'::regclass
          AND conname = 'ck_transfer_enforcement_receipt'
    ) THEN
        ALTER TABLE public.integration_transfer_events
            ADD CONSTRAINT ck_transfer_enforcement_receipt
            CHECK (
                (
                    enforcement_outcome IS NULL
                    AND enforced_at IS NULL
                    AND upstream_status_code IS NULL
                )
                OR (
                    enforcement_outcome = 'blocked_before_send'
                    AND allowed = FALSE
                    AND enforced_at IS NOT NULL
                    AND upstream_status_code IS NULL
                )
                OR (
                    enforcement_outcome = 'forwarded_upstream'
                    AND allowed = TRUE
                    AND enforced_at IS NOT NULL
                    AND upstream_status_code BETWEEN 100 AND 599
                )
                OR (
                    enforcement_outcome = 'delivery_unconfirmed'
                    AND allowed = TRUE
                    AND enforced_at IS NOT NULL
                    AND upstream_status_code IS NULL
                )
            );
    END IF;
END
$migration$;

COMMENT ON COLUMN public.integration_transfer_events.enforcement_outcome IS
    'NULL means evaluation only; non-NULL records controlled-egress '
    'execution-boundary evidence.';

COMMENT ON COLUMN public.integration_transfer_events.enforced_at IS
    'Time the controlled-egress enforcement outcome was recorded.';

COMMENT ON COLUMN public.integration_transfer_events.upstream_status_code IS
    'HTTP response observed from an allowed upstream request.';

COMMIT;

-- Complete migration 021's receipt validation under SQL NULL semantics.
-- CHECK accepts UNKNOWN unless IS TRUE explicitly excludes it.
-- Existing evaluation-only events retain their NULL receipt fields.
-- Invalid existing receipts cause this transaction to fail; no rows are changed.
BEGIN;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.integration_transfer_events'::regclass
          AND conname = 'ck_transfer_enforcement_receipt_complete'
    ) THEN
        ALTER TABLE public.integration_transfer_events
            ADD CONSTRAINT ck_transfer_enforcement_receipt_complete
            CHECK ((
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
            ) IS TRUE);
    END IF;
END
$migration$;

COMMIT;

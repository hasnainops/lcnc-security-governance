BEGIN;

ALTER TABLE public.approval_requests
    ADD COLUMN verified_reviewer_policy TEXT
    CHECK (
        verified_reviewer_policy IN (
            'lcnc-security-reviewer',
            'lcnc-senior-security-reviewer'
        )
    );

COMMIT;

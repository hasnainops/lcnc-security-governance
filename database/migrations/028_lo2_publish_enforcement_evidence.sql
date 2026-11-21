BEGIN;

ALTER TABLE access_decisions
    ADD COLUMN IF NOT EXISTS proxy_denial_verified_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS proxy_denial_http_status INTEGER;

ALTER TABLE access_decisions
    ADD CONSTRAINT ck_access_proxy_denial_evidence
    CHECK (
        (
            proxy_denial_verified_at IS NULL
            AND proxy_denial_http_status IS NULL
        )
        OR (
            proxy_denial_verified_at IS NOT NULL
            AND proxy_denial_http_status IS NOT NULL
            AND proxy_denial_http_status = 403
            AND proxy_denial_verified_at >= evaluated_at
            AND requested_action = 'publish_preflight'
            AND subject_id = 'appsmith-proxy'
            AND role = 'service'
            AND allowed = FALSE
            AND decision = 'deny'
        )
    );

COMMENT ON COLUMN access_decisions.proxy_denial_verified_at IS
'Trusted acceptance observation of HTTP denial at the governance proxy; not a preflight evaluation timestamp or native publication receipt.';

COMMIT;

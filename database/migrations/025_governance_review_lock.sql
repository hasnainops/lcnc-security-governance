-- Preserve application-first row locking without application write privileges
-- for the approval service. Only the explicit Vault workload grant may call it.
BEGIN;

-- Inherited grants keep ephemeral Vault users free of new function/column ACL
-- dependencies. Dropping a dynamic user removes its membership automatically.
DO $review_role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'lcnc_governance_review_access') THEN
        CREATE ROLE lcnc_governance_review_access NOLOGIN NOSUPERUSER NOCREATEDB
            NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    ELSIF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'lcnc_governance_review_access'
          AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'Existing governance review access role has unexpected capabilities';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles r ON r.oid = m.member
        WHERE r.rolname = 'lcnc_governance_review_access'
    ) THEN
        RAISE EXCEPTION 'Governance review access role must not inherit other roles';
    END IF;
END;
$review_role$;

CREATE OR REPLACE FUNCTION public.lock_application_for_review(target_id UUID)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $review_lock$
BEGIN
    PERFORM a.id
    FROM public.applications AS a
    WHERE a.id = target_id
    FOR UPDATE;
END;
$review_lock$;

REVOKE ALL ON FUNCTION public.lock_application_for_review(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.lock_application_for_review(UUID)
    TO lcnc_governance_review_access;
GRANT SELECT (application_id, source, observed_at) ON TABLE public.discovery_observations
    TO lcnc_governance_review_access;

COMMENT ON FUNCTION public.lock_application_for_review(UUID) IS
    'Locks one application until transaction end; returns no data and changes no rows. '
    'Approval routing uses this instead of granting the workload UPDATE on applications.';

COMMIT;

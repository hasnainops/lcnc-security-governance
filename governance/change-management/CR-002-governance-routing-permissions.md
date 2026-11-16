# CR-002: Approval routing database permissions

## Evidence and cause

The user's 2026-11-15 checkpoint proves that scheduled governance persisted
SECURITY_REVIEW decision `1c474d72-6b87-49ce-a537-7d0bd9a01319` for application
`fc05339a-c10c-4140-b3da-062f111aa65e`, but no linked approval request existed.
Healthy containers alone did not establish delivery to the reviewer queue.

The handoff patch added SELECT ... FOR UPDATE on applications to approval routing
and human decisions. The supplied Vault bootstrap grants the approval service
SELECT, but no UPDATE, on applications. A restricted PostgreSQL role with those
grants reproduces `permission denied for table applications` at route_application.
The human-decision freshness query also needs access to discovery timestamps.
The earlier handoff integration tests used the database owner and missed this
runtime permission boundary. Live logs are still needed to confirm whether this
is the only routing error on the Mac.

## Correction

- Migration 025 adds a fixed-SQL, SECURITY DEFINER function that only locks the
  specified application row until transaction end. It changes no data and returns
  no application fields. It uses a fixed search path and an explicitly qualified
  table, and revokes the default PUBLIC execute privilege.
- The approval service calls that function before reading current governance
  state. Application-first lock ordering and stale-review guards remain intact.
- The targeted Vault role updater preserves every existing role field and grant.
  It adds membership in the NOLOGIN role lcnc_governance_review_access. That role
  supplies EXECUTE on the one function and SELECT on only application_id, source
  and observed_at in discovery_observations. It grants no application writes or
  observation payload access and does not rotate AppRole credentials. Inherited
  grants avoid adding function/column ACL dependencies to ephemeral Vault users;
  a user can be dropped after the existing table/schema privilege cleanup.
- New database credentials get the added privileges. Only governance-automation
  needs an image rebuild/recreation. API replicas and Discovery already contain
  the retry path and can keep running during this change.
- The bootstrap script calls the updater for future provisioning after migration
  025. Do not run the full Vault bootstrap to deploy this correction.

Compatibility reference: HashiCorp's [PostgreSQL plugin source](https://github.com/hashicorp/vault/blob/main/plugins/database/postgresql/postgresql.go),
`defaultDeleteUser`, revokes table/schema/database privileges before dropping a
dynamic user. Inheriting the new access avoids adding direct function grants
that this default cleanup does not explicitly revoke. The local cleanup test
checks the relevant PostgreSQL behavior; the running Vault build remains subject
to live validation.

## Validation

Before the code correction, the restricted-role routing regression failed with
InsufficientPrivilege at the application row lock. After correction, 483 tests
passed, with six dependency/deprecation warnings and three subtests, on Python
3.12 and PostgreSQL 16.2 in an isolated database. This includes restricted-role
routing, human review, expiry rejection, same-decision retry after grant repair,
concurrent routing, row-lock conflict/release, denial of application/governance
writes and observation payload reads, denial of function execution to an
ungranted role, and cleanup of the dynamic role. Risk/OPA responses are explicit fixtures; these tests do not
represent live Mac acceptance or reviewer identity authorization.

The Docker recipe includes the new provisioning helper so its preservation test
runs in the existing PostgreSQL 18 isolated test environment. Run that suite on
the Mac before deployment.

## Apply and test on the Mac

Download `cr002-governance-routing-permissions.patch` into Downloads. This patch
is incremental to the applied automatic-governance handoff patch and the Docker
ignore correction already made in the preceding session. A failed patch check
must be resolved against current source; do not force application.

```bash
(
  set -e
  cd ~/Projects/lcnc-security-governance
  git apply --check "$HOME/Downloads/cr002-governance-routing-permissions.patch"
  git apply "$HOME/Downloads/cr002-governance-routing-permissions.patch"
  git diff --check
  docker compose -p lcnc-lo1-tests -f compose.lo1-test.yml \
    up --build --abort-on-container-exit --exit-code-from lo1-tests
)
routing_test_exit=$?
printf 'Routing permission test exit code: %s\n' "$routing_test_exit"
```

## Deploy after tests exit 0

This block saves a database archive and the current automation image before
changing the schema/role configuration. `pg_restore --list` verifies archive
readability; it is not a restore rehearsal. The role updater additionally saves
the prior Vault database-role configuration in a private directory under .git.
Existing history is retained. Do not create another test application.

```bash
(
  set -e
  cd ~/Projects/lcnc-security-governance
  umask 077
  routing_stamp=$(date -u +%Y%m%dT%H%M%SZ)
  routing_git_dir=$(git rev-parse --absolute-git-dir)
  routing_backup_dir="$routing_git_dir/cr002-routing-backups"
  mkdir -p "$routing_backup_dir"
  routing_backup="$routing_backup_dir/before-025-$routing_stamp.dump"
  routing_container=$(docker compose ps -q governance-automation)
  test -n "$routing_container"
  routing_image=$(docker inspect --format '{{.Image}}' "$routing_container")
  docker image tag "$routing_image" "lcnc-governance-automation-rollback:$routing_stamp"
  printf 'Automation rollback image timestamp: %s\n' "$routing_stamp"
  docker compose build governance-automation
  docker compose exec -T postgres sh -eu -c \
    'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$routing_backup"
  test -s "$routing_backup"
  docker compose exec -T postgres pg_restore --list < "$routing_backup" > /dev/null
  printf 'Database archive readable: %s\n' "$routing_backup"
  docker compose exec -T postgres sh -eu -c \
    'export PGOPTIONS="-c lock_timeout=5s -c statement_timeout=60s"; exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < database/migrations/025_governance_review_lock.sql
  python3 scripts/configure-governance-routing-grants.py
  docker compose up -d --no-deps --no-build --pull never \
    --force-recreate --wait --wait-timeout 120 governance-automation
  docker compose ps governance-automation governance-api-a governance-api-b discovery
)
routing_rollout_exit=$?
printf 'Routing permission rollout exit code: %s\n' "$routing_rollout_exit"
```

If the block fails, preserve its output and stop at that step. Do not retry Vault
SecretID recovery or run bootstrap automatically. This change concerns database
privileges; the prior AppRole login recovery was already verified.

## Live acceptance

Allow the next successful scheduled Discovery cycle to retry delivery. Do not
manually POST the route endpoint and present it as automatic-delivery evidence.
Use this read-only query, then repeat it after another completed cycle:

```bash
cd ~/Projects/lcnc-security-governance
docker compose exec -T postgres sh -eu -c \
  'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
BEGIN READ ONLY;
\x on
SELECT a.name, a.last_seen_at, a.governance_status, a.governance_outcome,
       gd.id AS governance_decision_id, gd.input_sha256,
       gd.created_at AS decision_created_at,
       ar.id AS approval_request_id, ar.status AS approval_status,
       ar.required_role, ar.created_at AS request_created_at
FROM applications a
JOIN governance_decisions gd ON gd.application_id = a.id
LEFT JOIN approval_requests ar ON ar.governance_decision_id = gd.id
WHERE a.id = 'fc05339a-c10c-4140-b3da-062f111aa65e'
ORDER BY gd.created_at DESC, gd.id DESC
LIMIT 3;
COMMIT;
SQL
```

Success is a non-NULL approval_request_id, pending status (unless a human already
acted), and Security/GRC Reviewer, linked to the current SECURITY_REVIEW decision.
If semantic inputs remain unchanged, the same decision/request IDs should survive
the following cycle. Changed inputs may legitimately produce a new decision.

If no request appears after a successful cycle, inspect automation logs for the
specific remaining error:

```bash
docker compose logs --no-color --since 10m --tail 100 governance-automation
docker compose logs --no-color --since 10m --tail 100 discovery
```

Record live results before advancing the assurance verdict. This patch repairs
queue delivery; it does not certify every LO1 criterion, approve a human review,
change the governed classification, or prove 24-hour temporal anomaly coverage.

## Rollback

If the new automation image has an unrelated regression, the saved timestamp
identifies its prior image. Restore that image using the existing Compose image
name and recreate only automation. The additive function and narrowly scoped
grants can remain for compatibility; the previous image still has the original
permission bug, so rollback restores the previous behavior rather than solving
the queue problem. Retain both assessment and governance/approval history.

# CR-002: recover rejected Governance Automation database credentials

## Problem and resulting behavior

The live approval training-gate request returned HTTP 500 at `psycopg.connect`:
PostgreSQL rejected the Vault-issued database user's password. No training SQL
had run. Governance Automation previously reused its cached credential until
the local deadline, with no recovery when the database rejected it earlier.
The trace establishes authentication failure; it does not establish why that
particular credential became invalid.

The service now invalidates the rejected cached pair, obtains a replacement
through its existing Vault AppRole/database-role path, and retries connection
establishment once. A concurrent late failure cannot discard another request's
replacement. Reads, refreshes and invalidations use the same cache lock.

The retry is limited to password rejection or a missing login role. Network,
TLS, host access configuration, SQL permission and statement failures are not
retried by this code. Both connection attempts have a five-second connection
timeout. No approval action or SQL transaction is replayed.

The cache also no longer imposes a 30-second minimum on a shorter lease. Its
deadline starts before the Vault credential request and includes an expiry
margin. Rejected replacement credentials are removed from the cache, and the
second authentication error is propagated. Vault failures also propagate.

This does not rotate SecretIDs, change Vault policy/TTL/role grants, change the
schema, complete training, or make a human review decision. An unavailable
Vault or unusable AppRole still requires its own recovery. This patch addresses
the observed service credential-recovery gap, not full LO1 acceptance.

## Verification

Before the fix, the focused suite reproduced ten failures, including rejection
of a still-cached login, concurrent recovery and short-lease over-caching.

After the fix, 21 focused tests passed. Real PostgreSQL tests use password
authentication and disposable restricted LOGIN roles to exercise expired
passwords, wrong cached passwords and deleted roles. The actual training-gate
handler and SQL return HTTP 200 while a mandatory incomplete assignment still
blocks approval; health also recovers. The existing approval stays pending,
no decision events are added, and application writes remain denied.

Vault responses in these tests are fixtures, not claims of live Vault recovery.
The local full suite passed 504 tests with three subtests on Python 3.12 and
PostgreSQL 16.2. Run the included Docker test project on the target system to
verify its Python 3.13/PostgreSQL 18 environment before rollout.

## Apply and test

From the repository root, after the routing-permissions patch:

```bash
git apply --check "$HOME/Downloads/cr002-automation-credential-recovery.patch"
git apply "$HOME/Downloads/cr002-automation-credential-recovery.patch"
git diff --check
docker compose -p lcnc-lo1-tests -f compose.lo1-test.yml \
  up --build --abort-on-container-exit --exit-code-from lo1-tests
```

Continue only if the tests return exit code zero. The Dockerfile and its own
ignore file include the new credential regression tests.

## Rollout

```bash
(
  set -e
  recovery_stamp=$(date -u +%Y%m%dT%H%M%SZ)
  recovery_container=$(docker compose ps -a -q governance-automation)
  test -n "$recovery_container"
  recovery_image=$(docker inspect --format '{{.Image}}' "$recovery_container")
  docker image tag "$recovery_image" \
    "lcnc-governance-automation-rollback:$recovery_stamp"
  printf 'Automation rollback image timestamp: %s\n' "$recovery_stamp"

  docker compose build governance-automation
  docker compose up -d --no-deps --no-build --pull never \
    --force-recreate --wait --wait-timeout 120 governance-automation
)
```

No database migration is needed. Verify `/health` and the existing approval's
`/training-gate` endpoint. An `approval_ready: false` response with blocking
assignments is a successful gate read, not a failed recovery. Review the listed
requirements rather than bypassing them. Preserve the existing decision and
request IDs as evidence of continuity.

## Rollback

Tag the recorded rollback image back to the image name reported for the
`governance-automation` service by `docker compose config --images`, then recreate
only that service with `--no-build --pull never`. Reverse this patch in the
working tree only after `git apply --reverse --check` succeeds. There are no
schema or Vault configuration changes to reverse. The old code will again lack
recovery from a rejected cached database login.

## References

Vault requires clients to renew or replace dynamic secrets as leases expire:
https://developer.hashicorp.com/vault/docs/concepts/lease

Psycopg documents SQLSTATE diagnostics and connection exceptions:
https://www.psycopg.org/psycopg3/docs/api/errors.html

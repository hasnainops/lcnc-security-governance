# CR-002: observed connectors through automatic assessment

## Problem and change

Fresh empty apps already reached configuration-snapshot inference. Non-empty apps
had two additional blockers: the collector emitted every saved datasource with an
unresolved destination, and both feature-assembly callers omitted server-derived
destination trust. Waiting for a 24-hour window cannot repair either path.

This increment extracts sanitized destinations from verified, referenced saved
datasources, evaluates their boundaries and host approval on the Governance API,
persists independent known counts, and automatically scores eligible snapshots.
It does not count inline actions as saved connectors or claim that observation
proves an executed transfer. No owner declaration, registration, approval request,
authoritative classification, credential or Vault grant is changed by the patch.

## Policy and evidence

- `CONTROLLED_EGRESS_APPROVED_HOSTS` is the existing server-owned egress host
  approval source. Matching remains exact, case-insensitive and trailing-dot
  normalized. Unset Compose configuration retains its existing `example.com`
  default; explicitly empty configuration now correctly means no approved hosts.
- DNS answers must all be public to establish an external destination. DNS
  failure, mixed public/private answers, unresolved or unsupported destinations
  retain unknown totals. Approval membership never overrides boundary checks.
- `DISCOVERY_INTERNAL_CIDRS` is optional and empty by default. Internal status
  requires all answers inside explicitly configured RFC1918/ULA lab subnets.
  Broad public ranges, loopback, link-local, multicast and mapped IPv6 answers
  do not become trusted internal integrations. Configure actual lab subnets only.
- DNS runs in a child process with a three-second deadline, eight workers and at
  most 64 unique DNS hostnames per application observation. Excess or failed
  resolutions remain unknown. IP literals do not require DNS. No HTTP request is
  made to the datasource destination. This is not a transfer authorization.
- Migration 026 adds `applications.discovery_feature_evidence`. It records the
  source observation, policy fingerprint, boundary, per-connector interpretation,
  pending reasons and semantic fingerprint. Snapshot and temporal assessment
  histories retain the evidence used for inference.
- A new observation with identical semantic evidence reuses the snapshot result.
  A changed policy or destination invalidates dependent outputs, including when
  aggregate counts happen to be equal. New facts are reconsidered on the next
  scheduled poll; DNS changes are not continuously watched between polls.
- `changes_last_24h` keeps its existing coverage requirements. Snapshot scoring
  uses only the four current-configuration features. It never substitutes zero
  for unavailable history or silently substitutes a snapshot for temporal proof.
- The collector version advances to `appsmith-discovery-v2`. A historical window
  spanning different collector versions remains unavailable, so improved
  extraction is not counted as an application change. Initial snapshot scoring
  remains available immediately.

Host-policy changes must be deployed consistently to both API replicas. Pause
discovery while replacing them. A CIDR observation boundary does not relax the
controlled-egress gateway's rejection of non-public transfer targets.

## Apply and test on the Mac

From `~/Projects/lcnc-security-governance`, with the patch saved in Downloads:

```bash
(
  set -e
  cd ~/Projects/lcnc-security-governance
  git apply --check "$HOME/Downloads/cr002-lo1-connector-policy.patch"
  git apply "$HOME/Downloads/cr002-lo1-connector-policy.patch"
  git diff --check
  PYTHONPATH="$PWD/discovery:$PWD/governance-api${PYTHONPATH:+:$PYTHONPATH}" \
    .venv/bin/python -m pytest -q tests
  docker compose -p lcnc-lo1-tests -f compose.lo1-test.yml \
    up --build --abort-on-container-exit --exit-code-from lo1-tests
)
lo1_connector_test_exit=$?
printf 'Connector policy verification exit code: %s\n' "$lo1_connector_test_exit"
```

The host test run may skip database tests; the isolated Compose test must pass
them. Its test Dockerfile and deny-by-default build-context allowlist are both
updated in this patch. Tests use explicit model replies for workflow assertions;
those replies are not evidence of real model accuracy or live Appsmith discovery.

## Deploy after those tests pass

This build uses the existing model, image bases and dependencies. It recreates
only the Governance API replicas and discovery. It does not rotate SecretIDs or
restart Vault, PostgreSQL or governance automation.

```bash
(
  set -e
  umask 077
  cd ~/Projects/lcnc-security-governance
  lo1_connector_stamp=$(date -u +%Y%m%dT%H%M%SZ)
  lo1_connector_dir="$(git rev-parse --absolute-git-dir)/cr002-connector-backups/$lo1_connector_stamp"
  mkdir -p "$lo1_connector_dir"
  for lo1_connector_service in governance-api-a governance-api-b discovery; do
    lo1_connector_container=$(docker compose ps -a -q "$lo1_connector_service")
    test -n "$lo1_connector_container"
    lo1_connector_image=$(docker inspect --format '{{.Image}}' "$lo1_connector_container")
    docker image tag "$lo1_connector_image" "lcnc-${lo1_connector_service}-rollback:${lo1_connector_stamp}"
  done
  printf 'Rollback image timestamp: %s\n' "$lo1_connector_stamp"
  docker compose build governance-api-a governance-api-b discovery
  docker compose exec -T postgres sh -eu -c \
    'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    > "$lo1_connector_dir/before-026.dump"
  test -s "$lo1_connector_dir/before-026.dump"
  docker compose exec -T postgres pg_restore --list \
    < "$lo1_connector_dir/before-026.dump" > /dev/null
  printf 'Database archive readable: %s\n' "$lo1_connector_dir/before-026.dump"
  docker compose exec -T postgres sh -eu -c \
    'export PGOPTIONS="-c lock_timeout=5s -c statement_timeout=60s"; exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < database/migrations/026_discovery_feature_evidence.sql
  docker compose stop discovery
  for lo1_connector_service in governance-api-a governance-api-b; do
    docker compose up -d --no-deps --no-build --pull never \
      --force-recreate --wait --wait-timeout 120 "$lo1_connector_service"
  done
  docker compose up -d --no-deps --no-build --pull never \
    --force-recreate --wait --wait-timeout 240 discovery
  docker compose ps governance-api-a governance-api-b discovery
)
lo1_connector_rollout_exit=$?
printf 'Connector policy rollout exit code: %s\n' "$lo1_connector_rollout_exit"
```

If a stage fails, retain its output and stop before the next stage. Keep the
rollback image timestamp. The additive column may remain if the application
images are rolled back; do not restore the database merely to revert this code.

## Runtime verification and the remaining LO1 evidence

First use the existing empty fresh-discovery app as a smoke check after the next
successful discovery cycle:

```bash
python3 scripts/verify-lo1-connector-policy.py \
  --application-id fc05339a-c10c-4140-b3da-062f111aa65e --allow-empty
```

For the next non-empty test, create a dedicated test app after saving a baseline.
Create a saved REST API datasource with a static public HTTPS base URL and an API
action referencing that saved datasource. An inline action by itself does not
satisfy the saved-connector identity requirement. Do not add real credentials,
customer records or embedded tokens. No manual call to the inference endpoint is
part of this test. Let the scheduled collector ingest and score it.

Run the same verifier with that app's inventory UUID, without `--allow-empty`, and
with `--expect-connectors 1`. Check `--expect-unapproved 0` or `1` against the
actual configured host policy, not an assumed default. The verifier makes GET
requests only and can save its JSON using `--output`.

Record the resulting application identity, source observation, counts, policy
fingerprint, real model assessment, classification and risk result. Then record
an unchanged poll, a real destination change, and one controlled failure/recovery.
These checkpoints establish the functioning connector path. They do not certify
all LO1 requirements, every LCNC platform, model accuracy or temporal coverage.

An unapproved destination and an ML anomaly are different signals. A single
unapproved connector may receive a non-anomalous model result. Keep that result
honestly; do not change a threshold or label simply to force a demonstration.
Model evaluation should include documented normal and suspicious configuration
cases, with limitations of the synthetic training data made explicit.

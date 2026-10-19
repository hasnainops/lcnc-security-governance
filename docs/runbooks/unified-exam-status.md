# Unified exam status — increment 1

This increment supplies Docker observations for all 20 existing services. It adds no dashboard UI yet and does not execute business workflows. The collector runs on the Mac; both API replicas read the same sanitized snapshot. Functional endpoint checks are explicitly `not_configured` in this increment.

Source checkpoint: `baseline-unified-exam-view-20261019` at `3179166`. The owner reported the baseline/design documentation commit as `b7a3006` on `feature/unified-exam-view`.

## 1. Verify before deployment

Use the existing project virtual environment. The collector itself uses only the Python standard library; its tests also require the existing API/test dependencies plus PyYAML (normally included by `uvicorn[standard]`). The CI validation job explicitly installs PyYAML.

```bash
cd ~/Projects/lcnc-security-governance
python -m pytest -q tests/test_platform_status.py tests/test_risk_engine.py tests/test_dependency_failures.py
docker compose config --quiet
python scripts/collect-platform-status.py --once
```

Each command must succeed before moving on. The one-shot collector exits nonzero if Docker is unavailable, commands time out, the Compose service catalog differs, or inspection output is invalid. The fixed command timeout is five seconds per call. A catalog mismatch must be investigated, not hidden by deleting catalog entries.

A successful collection does not mean every container is running. Inspect the snapshot:

```bash
python - <<'PY'
import json
from pathlib import Path

data = json.loads(Path('.runtime-observability/platform-status.json').read_text())
print('Collection:', data['collection_status'], 'Reason:', data['reason'])
print('Observed:', data['observed_at'])
for service in data['services']:
    print(service['service'], service['container_state'], service['docker_health'])
assert data['collection_status'] == 'ok'
assert len(data['services']) == 20
PY
```

This stage creates only an ignored observation directory/file. It does not recreate containers. Earlier availability checks are the comparison point, not a substitute for checking the new output.

## 2. Preserve the two API baseline images

Before rebuilding, preserve the API images recorded in the baseline. These commands refer to the observed local image IDs; if an ID is absent, stop and establish the current image identity instead of guessing.

```bash
docker image tag 9c6ab041c9bf lcnc-governance-api-a:cr001-baseline-20261019
docker image tag 0933212135e4 lcnc-governance-api-b:cr001-baseline-20261019
```

Keep those tags and images until the increment is accepted. This is a local recovery reference, not an off-machine backup. No database migration is introduced by this increment.

## 3. Keep collection running

In a dedicated terminal, from the project directory:

```bash
python scripts/collect-platform-status.py
```

Leave this process running during verification and demonstration. It refreshes about every 10 seconds and writes atomically. Stop it with Ctrl-C. It is deliberately foreground-operated for this first increment; no launch agent or hidden background job is installed.

The API considers observations older than 30 seconds stale. If Docker collection fails, the collector replaces old observations with an explicit unavailable result. If the process stops, its last file remains and ages into stale status. Neither condition becomes a current green result.

## 4. Deploy only the two changed API replicas

After the pre-deployment checks and image preservation pass, use another terminal:

```bash
cd ~/Projects/lcnc-security-governance
docker compose build governance-api-a governance-api-b
docker compose up -d --no-deps --wait --wait-timeout 90 governance-api-a
docker compose up -d --no-deps --wait --wait-timeout 90 governance-api-b
```

Run these in order and stop if any command fails. Keep one replica available while replacing the other. The snapshot directory must already exist from the collector; it is mounted read-only by both replicas. Existing Vault workload credentials must still work. These commands do not restart Vault or PostgreSQL.

No Docker engine is available in the review workspace, so real Compose validation, builds, container recreation, mount permissions, and cross-replica collection must be verified on the Mac. No successful live deployment is claimed by the patch.

## 5. Verify API and portal entry paths

While the collector is running:

```bash
curl -fsS --max-time 15 http://localhost:8000/exam/platform-status | python -m json.tool
curl -fsS --max-time 15 http://localhost:3000/api/exam/platform-status | python -m json.tool
```

Check both replicas directly from the existing API network:

```bash
docker compose exec -T governance-api-a python - <<'PY'
import json
from urllib.request import urlopen

for name in ('governance-api-a', 'governance-api-b'):
    with urlopen(f'http://{name}:8000/exam/platform-status', timeout=10) as response:
        data = json.load(response)
    assert data['observation_status'] == 'current', data['reason']
    assert len(data['services']) == 20
    print(name, data['observation_status'], data['observed_at'], data['summary'])
    with urlopen(f'http://{name}:8000/applications', timeout=10) as response:
        applications = json.load(response)
    assert isinstance(applications, list)
    print(name, 'inventory read:', len(applications), 'applications')
PY
```

`served_at` and observation age can differ across responses, and collection may advance between requests. Both replicas must read the shared snapshot contract and return a current observation under normal collection. The prior inventory had 14 applications; investigate unexpected changes rather than resetting the database.

HTTP 200 from the new route means an observation response was produced. Inspect `observation_status` and the per-service states. It is intentionally not a health-check endpoint; HTTP 200 does not assert that Docker or any service is healthy. Responses carry `Cache-Control: no-store`.

## 6. Verify stale handling without stopping services

Stop only the collector with Ctrl-C. After more than 30 seconds, request the new endpoint again. Expected: `observation_status` is `stale`, reason is `snapshot_stale`, and current summary counts such as `running` and `docker_healthy` are null. The last observed per-service values remain labelled stale.

Restart the collector. A successful fresh collection should restore `current`. Do not stop Docker or production-like services just to demonstrate this case.

## 7. Change record and rollback

Record the actual local test output, image preservation, collector result, direct replica results, portal-path result, and stale/recovery result in CR-001 before accepting this increment. Sonar and the wider regression gate remain release checks; local focused tests are not evidence of a new Sonar pass.

If deployment fails, stop before replacing the second replica. Use the preserved API images and the baseline Compose configuration to restore the affected replica, then verify inventory reads and the original service health checks. Keep the feature branch and diagnostic output for investigation. Do not delete volumes, reset the database, or restart Vault as a generic repair.

Docker CLI references used for the collector: [Compose project container listing](https://docs.docker.com/reference/cli/docker/compose/ps/) and [formatted container inspection](https://docs.docker.com/reference/cli/docker/inspect/). The collector first obtains IDs scoped to this Compose project, then requests only selected inspection fields. It never prints raw inspection data, Docker error bodies, environment variables, or health-check logs.

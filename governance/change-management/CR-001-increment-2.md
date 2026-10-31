# CR-001 — Increment 2: portal overview

Status: prepared and locally tested; Mac deployment and visual acceptance pending.
This is a supplement to [CR-001](CR-001-unified-security-governance-view.md), not a release approval.

## Baseline and scope

User-confirmed source baseline: `1f66fd2` on the historical implementation branch, pushed
with the baseline tag `baseline-unified-security-governance-view-20261019`.
The existing main branch is not changed by applying this increment.

Changes:

- Existing portal gains a platform observation panel, four separate counts,
  and an expandable catalog of all 20 services with their roles.
- Status is read from `/api/status/platform` every 10 seconds while the
  page is visible, with an explicit refresh button and a five-second timeout.
- Current counts disappear for stale, unavailable, malformed, or failed reads.
  Browser-side aging also prevents an old response from remaining current.
  A failed read is displayed immediately; this does not mask the intermittent
  `snapshot_missing` issue recorded in Increment 1.
- Running containers, Docker health, and unconfigured checks remain distinct.
  Functional probes remain unconnected and are labelled as such.
- Existing application inventory and histories remain on the page. A keyboard
  accessible selector, UUID context, retrieval time, empty states, and persistent
  read-error messages make the selected evidence explicit.
- Selection generations prevent older asynchronous responses from overwriting
  a newer selection. A governance action captures its application UUID and
  cannot be submitted twice while pending. Its completion does not switch the
  selected application. Mutations are not automatically retried.
- Inventory read failures clear counts and hide selected evidence rather than
  presenting old values as a successful refresh.

Only portal assets, its Dockerfile, two tests, and this record change.
No new containers, API routes, socket access, database changes, or dependencies
in the deployed portal. No approval/JIT/transfer controls or new functional
probes are delivered by this increment. Existing business behavior is retained.

## Validation completed in the review environment

- JavaScript syntax checks passed for both scripts.
- Six Node model tests passed: separate counts, local aging, unavailable data,
  exited containers, malformed/catalog responses, and backend catalog matching.
- DOM integration checks passed using jsdom 26.1.0: 20 service rows; stale,
  missing snapshot, HTTP/network failure and recovery; local aging; delayed
  selection responses; mutation binding/duplicate suppression; text escaping;
  and inventory error behavior.
- These checks use synthetic fixtures. They do not establish live Docker
  acceptance. Chromium download failed in the review environment, so rendered
  browser appearance and mobile layout remain unverified.

Reproduce the model tests with an installed Node.js runtime:

```bash
node --check governance-portal/app.js
node --check governance-portal/platform-overview.js
node --test tests/test_portal_overview.cjs
```

Optional DOM tests use a temporary dependency directory, not the runtime image:

```bash
portal_test_dir=$(mktemp -d)
npm install --prefix "$portal_test_dir" --no-audit --no-fund jsdom@26.1.0
NODE_PATH="$portal_test_dir/node_modules" node tests/portal_overview_dom.cjs
```

## Deployment and live acceptance still required

1. Apply the patch on a clean feature branch at `1f66fd2`; check the staged diff.
2. Confirm the host collector is running and current status reaches the portal.
3. Preserve the currently running portal image before building:

   ```bash
   portal_image_id=$(docker inspect --format '{{.Image}}' lcnc-governance-portal)
   docker image tag "$portal_image_id" lcnc-governance-portal:cr001-before-increment2
   ```

4. Build and recreate only the portal:

   ```bash
   docker compose build governance-portal
   docker compose up -d --no-deps --wait --wait-timeout 90 governance-portal
   ```

5. Open `http://localhost:3000` and reload. Confirm current counts against the API;
   expand the 20-service catalog and check the six unconfigured health checks.
6. Select two applications in quick succession. Confirm the selected UUID,
   application title and histories agree. Refresh inventory and confirm selection
   remains on the same application. Do not run a governance mutation solely for
   this read-only smoke test; the existing action still creates real records.
7. Stop only the collector with Ctrl+C. After more than 30 seconds, confirm stale
   labels and withheld counts. Restart it; confirm recovery, and record any
   `snapshot_missing` recurrence. Do not stop business containers for this test.
8. Check the page at a narrow browser width, verify keyboard selection and no
   clipped controls, and check browser console errors.
9. Record actual results here before committing; full CR-001 acceptance remains
   pending later increments and resolution of outstanding issues.

## Rollback

The deployment changes only the portal container. Keep the tagged old image.
To roll back the running portal, retag that preserved image under the Compose
image name and recreate the portal without building:

```bash
docker image tag lcnc-governance-portal:cr001-before-increment2 \
  lcnc-security-governance-governance-portal:latest
docker compose up -d --no-deps --force-recreate --no-build \
  --wait --wait-timeout 90 governance-portal
```

This rolls back the runtime image, not the working tree. Reconcile source on the
feature branch separately before a later build. API A/B and the collector remain
at Increment 1. Never delete database volumes as part of this rollback.


## Runtime and visual verification — 2026-10-20

- Mac validation: both JavaScript syntax checks passed; all six
  platform-overview model tests passed using Node 24 in Docker.
- Portal rebuilt and deployed independently; container became healthy.
- The platform-overview JavaScript asset returned HTTP 200.
- Served HTML contains the platform overview, application selector,
  and new script.
- Desktop screenshots confirm all 20 service rows and their roles:
  one running container each, 14 Docker-healthy, and six correctly
  labelled without configured Docker health checks.
- All service observations were labelled current in the reviewed table.
- Earlier stale-state screenshots correctly withheld current counts;
  current observations returned after restarting the host collector.
- Application selection and details were reviewed for Live Demo -
  Unapproved Integration and Expense approval, with distinct UUIDs.
- Unassessed application evidence remains distinguishable from
  container health.
- Functional probes and the complete unified solution workflow remain pending.
- The intermittent snapshot_missing issue from Increment 1 remains open;
  these successful observations do not establish its resolution.
- Narrow-window layout and oversized action-button presentation remain
  pending UI review.
- This verification does not establish a successful GitHub Actions run
  after the separate workflow-expression fix.


## Vault lockout recovery and portal checkpoint — 2026-10-20

- Both API replicas returned inventory HTTP 500 while their Docker
  health checks continued passing.
- Vault AppRole lockout was confirmed for governance-api,
  enterprise-discovery, governance-automation and appsmith-discovery.
- Fresh Secret IDs were issued and the affected roles unlocked.
  Lockout protection remained enabled; Vault was not restarted.
- Both API replicas, Caddy and the portal subsequently returned
  inventories containing 14 applications.
- Enterprise Discovery and Governance Automation health checks passed.
- Appsmith Discovery completed its 07:04:59 UTC cycle with three known
  applications and no authentication failure in that cycle.
- The 07:06 UTC portal screenshot confirmed current observations:
  20 running, 14 Docker-healthy, six without configured health checks,
  zero missing or multiple, and an inventory of 14 applications.
- Button alignment CSS was deployed; the Refresh status button was
  visually confirmed at normal height.
- Credential expiry versus use-limit exhaustion as the initial trigger
  remains unconfirmed. Durable credential lifecycle management is open.
- Host collector supervision, intermittent snapshot_missing,
  narrow-window verification and complete workflow acceptance remain open.
- This is an implementation checkpoint, not final CR-001 acceptance.
- No runtime credentials are included in this change record.

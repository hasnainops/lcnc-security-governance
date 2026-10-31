# CR-001 — Unified Security & Governance View

## Change record

| Field | Value |
| --- | --- |
| Date opened | 2026-10-19 UTC |
| Purpose | Demonstrate the existing LCNC MVP from the Governance Portal at `http://localhost:3000`, with service status, controlled actions, and their evidence in one interface. |
| Type | Planned functional enhancement to the existing MVP. This requires portal and API integration work; it is not just a diagram or styling change. |
| Status | Documentation committed on the Mac as `b7a3006`. Increment 1 code and local focused checks prepared; Mac collection, deployment, and live verification pending. |
| Change owner | Project owner; final reviewer for the solution demonstration. |
| Implementation branch | Historical feature branch created from `3179166017b2573d8883b478c06677cf94866121`; subsequent work is now integrated into `main`. |
| Current authorization | The project owner requested that work begin with a baseline and change-management plan. |
| Release condition | Reviewed changes, relevant checks, and a successful local solution rehearsal. No release is claimed by this record. |

## 1. Source baseline

Remote `main` was checked on 2026-10-19 and points to:

```text
3179166017b2573d8883b478c06677cf94866121
docs: align MVP architecture overview with implementation
```

This commit contains the revised architecture overview and SVG. The existing annotated tag `mvp-v5-demo-ready` resolves to the older commit `57596ebbf37243832d3de28413c536f7774ba42b`; preserve it unchanged. The project owner created the separate annotated tag `baseline-unified-security-governance-view-20261019` on the Mac and verified that it resolves to `3179166017b2573d8883b478c06677cf94866121`. The tag uses the UTC date; the user's local observation was on October 18 in America/New_York.

The baseline was reviewed in `docker-compose.yml`, `governance-portal/`, the API and automation routes, `monitoring/`, and the existing CI workflows. An isolated working branch was created from the exact source commit. No application code, runtime configuration, database schema, or policy was changed during baseline preparation.

The Mac checks supplied at 2026-10-18 23:31 America/New_York (2026-10-19 UTC) show `main...origin/main`, no changed or untracked files, HEAD at the exact baseline commit, and no errors from either working-tree or staged whitespace checks. The image listing is recorded below. The upstream status refers to the Mac's local tracking reference; the remote source was independently checked during baseline preparation.

At 23:34 America/New_York, the project owner confirmed creation of the historical implementation branch at that same commit. `git status --short --branch` showed the new branch with no file changes. Remote publication of this branch and baseline tag has not been confirmed.

This establishes a source reference and an observed image inventory, not a reproducible runtime snapshot. Preserve baseline images and the relevant private configuration/data recovery material before deploying changes. Do not infer that every running image was built from this exact source commit or that recording an image ID archives the image.

## 2. Observed runtime baseline

Evidence below is from the project owner's terminal output and screenshots on 2026-10-19 UTC. These checks were run on the Mac; they were not repeated against a separate review environment.

| Check | Observed result | What it establishes |
| --- | --- | --- |
| Docker engine | `29.6.2` | Docker is responding. |
| Compose services | All 20 running; none exited or unhealthy in the final listing | Container availability at that time. |
| Docker health checks | 14 healthy; six containers have no Docker health status | Do not label all 20 independently health-checked. Appsmith inherits its image health check. |
| API entry at port 8000 | Application inventory read succeeded; 14 applications | API entry and a database-backed read work. |
| Portal entry at port 3000 | `/api/applications` read succeeded; 14 applications | Portal proxy reaches the API. |
| API replicas | Direct inventory reads succeeded through A and B | Both replicas can read the database. |
| Internal service probes | Risk, ML, Scanner, DLP, Gateway, Enterprise Discovery, Automation, OPA passed | The tested health endpoints were reachable from API A. |
| Appsmith browser entry | Port 8080 returned HTTP 200 | Browser entry responds; this alone does not validate all Appsmith actions. |
| Appsmith discovery | Repeated successful cycles: three discovered, three known, zero shadow | Discovery authentication, polling, and the observed handoff are operating. |
| Grafana | Health API reported database `ok`; UI opened | Grafana responds. |
| SonarQube | System status `UP` | SonarQube responds; this does not establish a current quality-gate result. |
| Prometheus | All five configured targets `up` | The configured targets were being scraped. |

The five Prometheus targets are API A, API B, Integration Gateway, OPA, and Prometheus itself. They do not represent health coverage of all 20 containers. The current Grafana Service Availability panel includes only four of those targets and omits Integration Gateway.

### Service catalog

| Compose service | Role in the MVP | Docker health status in the supplied final listing | Reported image ID |
| --- | --- | --- | --- |
| `governance-portal` | Browser interface and API proxy | Healthy | `9544a61cb1bf` |
| `appsmith` | LCNC application platform | Healthy | `49eb0d096801` |
| `appsmith-proxy` | Browser entry for Appsmith | Not configured | `6b08c1b9858c` |
| `discovery` | Periodic Appsmith discovery | Not configured; successful cycles observed | `12ecc5c91dcc` |
| `enterprise-discovery` | Enterprise inventory ingestion and handoff | Healthy | `f6552e083854` |
| `governance-api` | Caddy entry for the Governance API | Healthy | `6b08c1b9858c` |
| `governance-api-a` | Governance API replica A | Healthy | `9c6ab041c9bf` |
| `governance-api-b` | Governance API replica B | Healthy | `0933212135e4` |
| `risk-engine` | Deterministic risk assessment | Healthy | `3a5e5edea2f4` |
| `ml-analytics` | Anomaly analysis and classification advice | Healthy | `86a1cf76e81f` |
| `security-scanner` | Application and workflow security analysis | Healthy | `ebb200eaf887` |
| `opa` | Governance and access policy decisions | Not configured; health endpoint passed | `8cdf42e73fb8` |
| `governance-automation` | Approval and JIT lifecycle | Healthy | `7412c41c76af` |
| `integration-gateway` | Transfer evaluation | Healthy | `6147317de3b3` |
| `dlp-engine` | Payload inspection for transfer evaluation | Healthy | `2705c436e933` |
| `postgres` | Inventory, decisions, and other persisted evidence | Healthy | `db676a0ed906` |
| `vault` | Workload authentication and managed credentials | Healthy | `ff11cc806267` |
| `prometheus` | Metrics collection | Not configured; targets checked | `26bf7bb2ea9e` |
| `grafana` | Metrics dashboards | Not configured; health API checked | `6ab635abac7d` |
| `sonarqube` | Code quality and security analysis | Not configured; system API checked | `ab483559746c` |

Image IDs above are the abbreviated local IDs from `docker compose images`, not registry digests. All listed images are ARM64; Caddy, PostgreSQL, and SonarQube were reported as `linux/arm64/v8`. Full IDs and retained baseline images remain part of deployment preparation. The image listing does not itself repeat the earlier health checks.

### Known limitations and recovery dependency

- Vault AppRole login previously returned HTTP 403 for the affected workloads. Running the existing Vault bootstrap restored configuration and fresh workload credentials; subsequent checks passed. The configured development Vault loses its configuration across restart, so recovery may require that bootstrap again.
- Some discovered applications lack metadata needed for ML anomaly analysis or classification. The new interface must retain a clear pending state and identify the missing inputs.
- The Grafana view showed empty or zero business counters after recovery. Those metrics are not a substitute for persisted decision history, and their absence is not proof of a completed workflow.
- The full approval, training, JIT, DLP, controlled-egress, and failure-path demonstrations have not been rerun in this recovery session. Neither has the full test suite or a fresh Sonar quality gate.
- Historical test counts and earlier milestone passes remain historical evidence. They must not be reported as fresh checks of this change.

## 3. Scope and architecture constraints

Extend the existing portal and backend integration. The default target remains the existing 20-container topology. Any additional runtime component must be justified and recorded before implementation.

| Area | Intended addition |
| --- | --- |
| Platform status | All 20 services listed with source, last observation, container state where available, and a distinct functional check result. |
| Application context | Selected application, owner, metadata completeness, current evidence, and stale or missing evidence clearly visible. |
| Analysis and governance | Trigger existing analysis and governance operations and display the actual returned decisions and reasons. |
| Approval and training | Inspect and operate the existing approval and required-training lifecycle with attributable actions. |
| JIT and access | Request, approve/revoke, and inspect temporary access; display actual access-policy decisions and expiry. |
| Transfer demonstration | Inspect destination and DLP evaluation, deliberately invoke permitted execution, and distinguish evaluation from delivery. |
| Evidence and monitoring | Application history, action results, and a compact metrics summary within the portal; native administrative interfaces remain available for deeper inspection. |

Preserve these implementation boundaries:

1. Caddy exposes the Governance API, implemented by two replicas. New portal integrations use controlled backend routes.
2. ML, Risk Engine, and Security Scanner remain separate services. Governance evaluation does not imply that every analysis ran afresh.
3. OPA governs policy and access decisions; Automation manages approvals and JIT. `AUTO_APPROVE` still enters the existing human-confirmation lifecycle.
4. Gateway and DLP evaluate transfers. Only the Governance API performs the external request after an allowed evaluation. Evaluation success must not be presented as successful external delivery.
5. Compliance, guidance, and training remain within the API boundary. PostgreSQL and Vault remain supporting dependencies.
6. Monitoring and DevSecOps are separate from the synchronous business workflow. A normal business request does not traverse all 20 containers.
7. Preserve Appsmith network isolation, server-side destination validation, policy denial precedence, dependency failure handling, and required training checks.

Production SSO, a new enterprise deployment, broad policy redesign, new discovery vendors, arbitrary service administration from the browser, and an overhaul of native Grafana/Sonar/Vault interfaces are outside this change.

## 4. Design decisions and implementation constraints

The implementation design, page sections, endpoint mapping, and initial status contract are recorded in [Unified Security & Governance View design](../../architecture/unified-security-governance-view-design.md). Proposed routes and status collection described there are not existing runtime capabilities yet.

### A. Truthful service status

Current Prometheus coverage cannot provide all-container status. The selected initial design is a narrow host-side collector that reads only allowlisted container state and emits a sanitized snapshot for backend consumption. It preserves the 20-container topology without mounting the Docker socket into the portal or API.

This collector is not implemented yet. The design specifies a host process, a directory mounted read-only by both API replicas, a 10-second collection interval, and a 30-second stale threshold. Missing collectors, missing containers, and expired observations must display unavailable, missing, or stale rather than healthy. Service reachability and business readiness require separate evidence.

### B. Actions and evidence

Map each solution action to its existing endpoint, required inputs, side effects, and persisted evidence. Extend API integration only where needed. Any new proxy must have fixed upstreams and a bounded route set, not accept arbitrary target URLs.

Prevent accidental repeated submissions and show failure or partial completion explicitly. Demo actions can add real decisions, training assignments, approvals, and grants to PostgreSQL. Use identified solution applications and retain their evidence. An actor field records the stated actor; do not present it as authenticated enterprise identity.

The current controlled-egress path persists transfer evaluation and returns the external execution result, but does not separately persist that delivery result. Initially label that result as belonging to the current action. Durable delivery history would require a separately documented additive API/database change within this record.

### C. History versus progress

Show timestamps and actual persisted or returned evidence. A history view is not a distributed trace. Do not animate success for services that were not invoked or infer precise step timings from a single final response. If correlation across requests or replicas is required, define and test it explicitly.

## 5. Change stages and gates

| Stage | Deliverable | Exit condition |
| --- | --- | --- |
| 0 — Baseline | This record; source reference; Mac Git status and image identities; existing data/configuration recovery plan | Known source and runtime references recorded; unrelated local changes preserved; baseline tag created without moving old tags. |
| 1 — Design | Page structure, service catalog, status-source contract, action-to-endpoint/evidence mapping | Every displayed status and workflow action has a named source and clear missing/error behavior. |
| 2 — Read-only view | Service overview, application context, history, and monitoring summaries | Accurate data, freshness, partial-failure behavior, and existing portal behavior demonstrated. |
| 3 — Controlled actions | Analysis, governance, approval, training, JIT, and transfer controls | Actual results displayed; repeated clicks handled; existing policy and trust boundaries preserved. |
| 4 — Validation | Focused tests, relevant existing regressions, CI results, and local integration evidence | Changes pass the applicable gates below, including negative paths. |
| 5 — Solution rehearsal | Repeatable local demonstration from port 3000; evidence and limitations reviewed | Planned solution journey completes from the portal without switching native service tabs. |
| 6 — Release and slides | Reviewed merge, release tag, updated architecture/supporting views where affected, final slides | Documentation describes the tested released behavior; rollback reference retained. |

Use small commits by stage, for example baseline documentation, status API, read-only portal, workflow actions, tests, and demo documentation. Keep the stable source reference intact. Changes were prepared on the historical implementation branch, reviewed, and then integrated into `main`.

A pull request is the review record. Do not assume a GitHub ruleset or required-review protection is currently configured. The existing workflows run on pull requests, but their test lists do not cover every current test file or this proposed interface. Update relevant test coverage and workflow configuration as part of implementation rather than assuming existing green checks prove the new view works.

## 6. Acceptance and validation

| Gate | Required evidence |
| --- | --- |
| Availability coverage | All 20 services accounted for; container state distinguished from endpoint health; missing and stale data visibly handled. |
| Single solution entry | The agreed demonstration can be performed at `http://localhost:3000`; native UI links are optional investigation tools. |
| Workflow accuracy | Real analysis, risk/policy outcome, approval, training, JIT/access, and transfer results for the selected solution application; skipped and pending steps identified. |
| Control preservation | OPA denial precedence, approval/training restrictions, JIT expiry/revocation, destination validation, dependency failures, and blocked transfers retain their established behavior. |
| Evidence integrity | Application identity, action, result, time, and source are clear; durable history distinguished from transient results and metrics. |
| Safe integration | No credentials in browser responses or status snapshots; no Docker socket in the portal/API; fixed backend destinations; existing network boundaries retained. |
| Regression | Existing inventory, portal evaluation/history, discovery, and both API replicas still work. Run affected tests and the relevant established security/control suite. |
| Build and CI | Valid Compose configuration; applicable Python/OPA checks; meaningful tests for new status/actions; relevant security scans and Sonar gate reviewed. Add browser interaction checks for the new solution journey and failure states. |
| Local rehearsal | User's Mac runs the changed services successfully; one successful and appropriate negative scenario are recorded for each changed control path. |

Tests should resolve concrete risks. Do not add tests that only mirror markup or rerun unrelated suites repeatedly without a reason. Increment 1 focused results are recorded below; the remaining acceptance and release gates are still pending.

## 7. Rollback and data protection

Before the first runtime deployment, record image IDs for the services being replaced and retain a path to their baseline images. Capture a PostgreSQL backup before any schema migration or demo setup that changes important data. Keep local credential/configuration recovery material private and out of Git.

Rollback restores the recorded code, configuration, and images for affected services, then repeats the baseline availability and inventory checks. Avoid deleting Docker volumes or resetting unrelated work. A source tag alone is insufficient to recover a build if its base image or dependencies have changed; preserve the relevant image references.

Code rollback does not undo approval decisions, training completion, access grants, external deliveries, or other database effects already produced. Revoke demo grants through the normal lifecycle where needed. Preserve evidence and use a separately planned data restore only when justified. Prefer backward-compatible additive schema changes if a migration becomes necessary.

Vault development restart can require `scripts/bootstrap-vault.sh` and fresh workload credentials. It is not a reason to commit `.env`, `.runtime-secrets`, tokens, or passwords. Do not use `docker compose down -v` as a rollback mechanism.

## 8. Immediate next step on the Mac

At this stage, the baseline tag, feature branch, and documentation commit already existed. Subsequent increments were completed on the historical implementation branch before integration into `main`.

The project owner confirmed the documentation commit `b7a3006` and a clean feature branch. The next patch introduces increment 1: the collector, shared status contract, API route, two read-only directory mounts, CI coverage, and the [local verification runbook](../../docs/runbooks/unified-security-governance-status.md). Apply that patch, run the focused tests and a one-shot collector, then inspect the output before deploying the API replicas. Image preservation and data/configuration recovery preparation remain deployment gates.

### Increment 1 implementation evidence

The collector uses fixed project-scoped Docker commands and selected inspection fields. Both API replicas read `/run/observability/platform-status.json`; no Docker socket is mounted. A new `GET /status/platform` route returns all 20 service entries, observation freshness, and explicit unknown/missing/multiple states. Fresh summary counts are withheld when the observation is stale or unavailable. Business endpoint checks remain `not_configured` until a later increment.

Prepared changes are limited to the collector and contract modules, API route registration, two Compose mounts, the ignored snapshot directory, tests/CI, and documentation. No policy, approval, database schema, or outbound-execution logic was changed.

Validation in the review workspace: 44 focused tests passed under Python 3.13.16, including existing risk and dependency-failure checks. The actual Governance API route was exercised through an HTTP test client and correctly returned unavailable observation without a snapshot. The test client emitted an upstream deprecation warning. Compose catalog and mount structure were checked from YAML. This workspace has no Docker engine; real CLI collection, `docker compose config`, image builds, live mounts, both running replicas, and the portal proxy remain Mac acceptance checks. A fresh Sonar quality gate and full release regression are not claimed.

## 9. Change log

| Date (UTC) | Event | State |
| --- | --- | --- |
| 2026-10-19 | Remote source, runtime evidence, existing portal coverage, Compose catalog, monitoring, and CI scope reviewed | Baseline record prepared. |
| 2026-10-19 | Historical implementation branch created from `3179166` in the review workspace | Documentation only; no Mac changes or remote push performed. |
| 2026-10-19 | Mac working tree confirmed clean on `main` at `3179166`; both whitespace checks passed; image IDs for all 20 containers recorded from user output | Ready for the Mac source tag and feature branch; runtime image preservation and data recovery preparation remain later deployment gates. |
| 2026-10-19 | Mac baseline tag verified at `3179166`; historical implementation branch confirmed clean | Source checkpoint complete; no remote publication claimed. |
| 2026-10-19 | Dashboard sections, status contract, action mapping, evidence limits, and implementation increments documented | Design prepared for the first documentation commit; runtime implementation pending. |
| 2026-10-19 | Owner confirmed documentation commit `b7a3006` and a clean feature branch | Baseline/design commit complete on the Mac. |
| 2026-10-19 | Increment 1 collector/API contract implemented and 44 focused tests passed on Python 3.13.16 | Patch prepared; live Mac verification and deployment pending. |


## Increment 1 runtime verification — 2026-10-19

- Automated validation: 44 tests passed; one upstream deprecation warning.
- Both API replicas deployed and passed inventory reads: 14 applications each.
- Both replicas see the same snapshot through read-only observability mounts.
- Observed platform: 20 running containers, 14 Docker-healthy,
  six without configured Docker health checks.
- Caddy and portal paths passed five requests each with matching timestamps.
- Stale-data handling passed: service observations become stale and current
  summary counts are withheld.
- Immediate refresh recovery intermittently returned snapshot_missing.
  Root cause remains unconfirmed; this is an open acceptance issue.
- Three subsequent refresh cycles passed through both public entry paths.
- Continuous collection produced five distinct current snapshots across
  70 portal requests, with zero failed reads.
- A transient Caddy 502 during replica recreation recovered; this deployment
  does not establish zero-downtime rollout.
- Continuous collection currently requires a running host terminal process.
- Increment 1 provides the collector and API endpoint. The unified portal UI
  and complete workflow acceptance remain pending.

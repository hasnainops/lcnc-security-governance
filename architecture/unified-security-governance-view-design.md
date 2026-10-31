# Unified Security & Governance View — implementation design

Status: planned design for CR-001; no features in this document have been deployed by the documentation patch.

Implementation update: increment 1 prepares the Docker status collector and API route. Functional probes remain explicitly `not_configured`; portal UI and workflow integrations are later increments. See the [increment 1 runbook](../docs/runbooks/unified-security-governance-status.md) for actual checks and deployment steps. Live Mac verification is still pending.

Source examined: `3179166017b2573d8883b478c06677cf94866121`. The implementation is now integrated into `main`. Change control, baseline evidence, acceptance, and rollback are in [CR-001](../governance/change-management/CR-001-unified-security-governance-view.md).

## 1. User experience

Use the existing Governance Portal at `http://localhost:3000`. Keep the selected application visible while navigating sections inside the same page. Platform status is global; workflow results belong to the selected application. Show evidence timestamps, source, and missing inputs next to results.

| Section | What the examiner sees | Main data source |
| --- | --- | --- |
| Platform overview | All 20 containers, Docker state, Docker health where configured, endpoint checks, and observation age | New sanitized host snapshot; bounded backend checks; existing Prometheus targets |
| Inventory and discovery | Discovered applications, platform, owner, registration, last seen, observed workflow, and metadata completeness | Existing Governance API application records and history |
| Analysis and governance | Separate ML anomaly, classification, and scanner actions; risk and OPA results; governance outcome and reasons | Existing API analysis and governance routes |
| Reviews and training | Pending review, required role, human decision, assigned training, completion, and training gate | Automation lifecycle through new API adapters; existing API training routes |
| Temporary access | JIT request, approval/rejection, grant, revocation/expiry, and access-policy result | Automation JIT routes through new API adapters; existing API authorization route |
| Transfers | Destination, evaluation verdict, DLP findings, and a separate deliberate external execution action | Existing API transfer routes; Gateway and DLP remain downstream evaluators |
| Evidence and monitoring | Persisted application history, current action results, lifecycle records, selected metrics, and tooling availability | Existing history and lifecycle sources; bounded Prometheus queries; health probes |

Use compact summaries with expandable details rather than placing every technical field on screen. One selected application and one pending action should remain unambiguous. A successful control block is an expected security outcome, not a broken service.

Native Appsmith, Grafana, Prometheus, SonarQube, and Vault interfaces remain optional investigation tools. The planned governance journey should use the portal without requiring those tabs. Editing Appsmith applications and administering Vault/Sonar remain native-tool operations outside that journey.

## 2. Integration boundaries

The browser keeps its existing same-origin `/api/` path. Nginx forwards that path to Caddy, which routes to API A or B. New orchestration adapters belong in the Governance API and call fixed internal destinations. Do not add a generic URL proxy or allow arbitrary browser-supplied PromQL.

The design retains all existing 20 containers. It adds one small host process for observation, not an additional container. Both API replicas must see the same status snapshot; do not store correctness-critical dashboard state only in one replica's memory.

The API remains the external execution point. Approval/JIT decisions remain owned by Automation; analysis by the existing analysis services; policy by OPA; transfer evaluation by Gateway and DLP. This interface does not replace those control implementations.

## 3. Platform status contract

### Collection and delivery

Implement a standard-library Python host script, proposed as `scripts/collect-platform-status.py`. Run it from this repository during a demo, with an explicit start/stop command and a one-shot mode. It needs the existing Docker CLI; it should not need new host Python packages.

- Scope Docker queries to this Compose project and the exact 20-service catalog. Collect container state, Docker health status if present, observation time, and image ID. If a service has an unexpected number of containers, report that fact rather than choosing one silently.
- Never copy environment variables, credentials, mounts, raw inspection output, or health-check log bodies into the snapshot.
- Collect every 10 seconds. Use bounded subprocess timeouts; a failed Docker query is unavailable observation, not evidence that every container stopped.
- Write a versioned JSON snapshot atomically into `.runtime-observability/platform-status.json`. Ignore the directory in Git. Mount the directory read-only at `/run/observability` in both API replicas; mounting the directory allows atomic file replacement to be observed.
- Proposed API route: `GET /status/platform`. The browser reaches it as `/api/status/platform`. The API reads a fixed file path, validates its schema and size, and returns only allowed fields.
- Keep the API and portal free of Docker socket mounts. The host collector must not expose a command-execution HTTP endpoint.
- Poll the status route every 10 seconds while the overview is visible. Mark observations older than 30 seconds stale. A future-dated, malformed, oversized, or missing snapshot is unavailable; the UI must not retain a green status from it.
- A stale snapshot may remain visible with its old timestamp and stale label, but must not contribute to a current healthy count. Include an explicit refresh button.

Proposed response fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Contract version, initially 1 |
| `observed_at` | Collector observation time in UTC |
| `served_at` | API response time in UTC |
| `observation_status` | Current, stale, or unavailable observation |
| `services` | Exactly the 20 expected service entries, including missing services |
| Per-service `container_state` | Running, exited, restarting, paused, missing, or unknown; preserve other observed Docker states explicitly |
| Per-service `docker_health` | Healthy, unhealthy, starting, not configured, or unknown |
| Per-service `observed_at` | Timestamp belonging to this service observation |
| Per-service `functional_check` | Separate check result, source, time, and limited explanation, if a check exists |

Endpoint checks are distinct observations. Add bounded, cached checks for the existing service health endpoints, database-backed reads for the API replicas, and host-accessible tooling endpoints. Use fixed targets and timeouts. Preserve Appsmith isolation: API A/B cannot be assumed to reach Appsmith directly; its browser-entry check can be collected through the existing host proxy. The same constraint applies to host-only access paths.

For services without a functional check, say so. Discovery container state alone does not prove successful polling. Show application last-seen/observed workflow evidence separately. If a dedicated discovery heartbeat is added later, define and validate that evidence explicitly.

The 20-service catalog is the one recorded in CR-001 and `docker-compose.yml`. Test catalog drift so a later service addition cannot disappear from the dashboard silently.

### Failure display

| Observation | Required display |
| --- | --- |
| Running container without a Docker health check | Running; health check not configured |
| Healthy Docker check, functional probe failed | Show both observations; functional check failed |
| Healthy response from `/health`, database read failed | Process responds; database-backed request failed |
| Collector stopped or snapshot stale | Observation stale/unavailable; do not infer all services failed or passed |
| API/Caddy unreachable | Portal displays API connection failure; do not fabricate a backend response |
| Missing application metadata | Analysis pending, with the actual missing fields |
| Prometheus series absent | No metric sample; do not silently invent a zero |

## 4. Existing API actions

In this section, `A` means `/applications/{application_id}` at the Governance API. Browser requests add `/api` in front. These routes already exist at the baseline commit; the new work is the UI, validation, error display, and integrations explicitly called out below.

| Portal operation | Existing API route | Result and important limit |
| --- | --- | --- |
| List/select an application | `GET /applications`; `GET A` | Current application records; identify by UUID, not display name alone |
| Update supported application metadata | `PATCH A` | Current update model supports business/classification/integration fields; updates stale existing assessments |
| Run anomaly analysis | `POST A/ml-analyze` | Fresh analysis only when required inputs exist; otherwise show actual pending/error response |
| Request classification advice | `POST A/ml-classify` | Advisory classification; do not silently overwrite the authoritative classification |
| Run security scan | `POST A/security-scan` | Findings, severity, evidence, remediation, and scan state |
| Assess risk separately | `POST A/assess` | Deterministic risk result; not a complete governance workflow |
| Evaluate governance policy separately | `POST A/policy-evaluate` | OPA decision and reasons; not an approval or an execution action |
| Run governance | `POST A/governance-evaluate` | Risk, policy, governance decision, approval-routing result, and training-assignment result |
| Read history | `GET A/history` | Persisted assessment/decision records, including transfer evaluations and access decisions |
| Show control evidence | `GET A/compliance-evidence`; `GET /compliance/controls` | Current control evidence and framework mappings |
| Show dynamic compliance | `GET A/compliance/dynamic` | Current computed compliance result |
| Save compliance assessment | `POST A/compliance/dynamic/assess` | New persisted compliance assessment |
| Show citizen guidance | `GET A/citizen-guidance` | Guidance, security score, and training recommendations |
| Read training | `GET A/training/assignments`; `GET A/training/status?subject_id=...` | Assignment/completion state for the actual application and subject |
| Assign required training | `POST A/training/automation/run` | Runs existing assignment logic; a deliberate action |
| Complete training | `POST A/training/complete` | Requires `subject_id` and `module_id`; records completion through existing logic |
| Evaluate access | `POST A/authorize` | Requires `subject_id`, `role`, and `action`; evaluates access and persists a decision; does not perform the requested business action |
| Evaluate a transfer | `POST A/evaluate-transfer` | Requires destination URL; optional content and field names; persists evaluation, with server-derived trust |
| Execute controlled egress | `POST A/controlled-egress` | Deliberate POST execution after a fresh allowed evaluation; show actual returned execution result |

`Run governance` freshly assesses risk and policy, reads stored anomaly evidence, determines the outcome, attempts approval routing, and attempts training assignment. It does not automatically rerun ML, classification, or the scanner. Show `routing_error` or `assignment_error` as partial completion even when a governance decision was saved.

The current update model does not accept the five telemetry counters reported missing by discovery. Do not show a form that pretends those values were saved. Start with existing validated inputs and clearly identified demo data. Any additional telemetry editor needs an explicit API model, persistence and staleness design before it is connected.

## 5. Automation adapters needed

Add explicit Governance API routes under `/automation/` for the allowlisted operations below. The exact adapter request models must match the underlying Automation schemas. Preserve error codes and useful safe error details; do not convert a rejected decision into HTTP 200 success.

| Function | Existing Automation route at `http://governance-automation:8007` |
| --- | --- |
| List approval requests | `GET /approvals` |
| Show escalation state | `GET /escalations` |
| Read an approval training gate | `GET /approvals/{approval_id}/training-gate` |
| Approve/reject/request changes | `POST /approvals/{approval_id}/decision` |
| Recover failed approval routing deliberately | `POST /applications/{application_id}/route` |
| List/create JIT requests | `GET /privileges/requests`; `POST /privileges/requests` |
| Approve/reject a JIT request | `POST /privileges/requests/{request_id}/decision` |
| List grants | `GET /privileges/grants` |
| Revoke a grant | `POST /privileges/grants/{grant_id}/revoke` |
| Check a matching active grant | `GET /privileges/check` with application, subject, and action |

The existing expiry/escalation workers remain authoritative. No browser button should force an unexpired grant to expire or bypass an approval. A manual maintenance trigger, if exposed, must use the existing expiry/escalation operation and retain its real semantics.

Decision and revocation actions require an actor and reason. These are recorded actor claims, not enterprise-authenticated roles. JIT requests require an application UUID, subject, base role, requested action, justification, and duration; existing duration limits are 5–480 minutes.

Current approval and JIT request lists are globally limited; filtering the returned page in the browser could falsely suggest an application has no records. Add backward-compatible application filtering before limits where needed, with tests, and use that filter through the API adapters. Preserve existing callers and response shapes.

Some existing GET routes perform lifecycle maintenance: training reads refresh overdue assignments, and grant listing expires eligible grants. The initial platform/inventory view should not call those routes as health probes. Lifecycle panels may use them with their established semantics; do not describe all GET operations as side-effect free.

## 6. Evidence and observability

Reuse `GET A/history` for risk, ML, classification, scanner findings, transfer evaluations, access decisions, compliance assessments, OPA decisions, and governance decisions. Use real record IDs and timestamps. Show current approval/training/JIT records alongside history with their own source labels.

Training, approval, and privilege event tables exist separately. A complete combined lifecycle event timeline needs additional read routes; it is not delivered by the current history endpoint. Start with the existing histories and lifecycle records. Extend event reads only with explicit application scoping, ordering, and bounded responses. Never reconstruct missing events as facts from the current state alone.

Treat current browser action results separately from persisted history. Controlled-egress delivery results are currently returned but not stored separately; retain that distinction after refresh. Do not display a stored allowed evaluation as proof of successful external delivery. Do not store sensitive payloads, credentials, or raw service logs in browser persistence or a new dashboard history.

Add a small API metrics-summary route backed by fixed Prometheus queries for the existing five scrape targets and selected governance metrics. Cache briefly and time out calls. Preserve no-data and source-error states. The baseline Grafana availability expression omits Gateway; correct that scoped coverage gap during the monitoring increment.

SonarQube `UP` means the server responds. It is not a quality-gate verdict. CI results or quality-gate evidence shown in the portal must include an actual result, source commit, and timestamp; leave them unavailable until a real source is connected. Do not request a new Sonar scan on each page refresh.

## 7. Action safety and repeatability

- Bind every action to the displayed application UUID. Retain its result under that UUID even if the user changes selection while a request is in flight.
- Disable duplicate submissions while an action is pending. Do not automatically retry a timed-out mutation; it may already have completed. Refresh relevant evidence and explain uncertainty before another deliberate attempt.
- Require a clear, deliberate action for approvals, revocations, training completion, metadata updates, and external delivery. Display intended destination and synthetic demo payload before delivery.
- Render backend strings as text rather than unsafe HTML. Keep the portal's same-origin restrictions and existing security headers.
- Preserve policy denials, training restrictions, JIT semantics, destination validation, and dependency failure behavior. The dashboard is a client of those controls.
- Use designated reference applications and synthetic data. Registration, assessment, training, and approval actions create real local records; a repeatable demo must account for them.
- Show empty, pending, stale, failed, blocked, and unavailable states explicitly. Do not infer business success from all-green service cards.

## 8. Implementation increments

| Increment | Primary changes | Verification before proceeding |
| --- | --- | --- |
| 1 — Status contract | Host collector, fixed snapshot schema, read-only API route, ignored runtime directory, mounts for both replicas | Missing Docker, malformed/stale/future snapshot, missing/duplicate services, no secret fields; equivalent response through both replicas |
| 2 — Portal overview | Service catalog, application selector/context, existing histories, refresh and error handling | Accurate service counts and freshness; API failure; selection changes; existing portal behavior preserved |
| 3 — Analysis controls | ML/classification/scanner/risk/policy/governance and supported metadata forms | Actual persisted/returned outcomes; missing metadata; separate analyses; partial workflow failure; no duplicate automatic writes |
| 4 — Lifecycle controls | Automation adapters, application filtering, training, approvals, JIT/access | Approval denial, training gate, role/action validation, expiry/revocation, unknown request IDs, upstream failure |
| 5 — Transfers and evidence | Separate evaluate/execute controls, evidence integration, bounded metrics summary | Blocked destinations, DLP denial, dependency failure, successful controlled execution to an approved demo target, transient versus persisted result handling |
| 6 — Rehearsal and release | Existing regression gates, full local validation sequence, documentation and slide updates | Baseline availability retained; validation paths and negative controls demonstrated; reviewed release and rollback reference |

The first documentation commit contains only this design and CR-001. Runtime changes begin with increment 1 after that record is in the feature branch. Stage-specific implementation commits must update the record with actual files changed, verification performed, and any deviations from this design.

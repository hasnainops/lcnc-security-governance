# CR-002 — LO3 Risk and Governance Acceptance

## Acceptance metadata

- Acceptance date: 2026-11-21
- Branch: audit/learning-objective-assurance
- Scope: Existing LCNC governance MVP
- Result: Scoped functional acceptance completed
- Operational deployment: Governance Automation and Governance Portal
- Production certification: Not claimed

## 1. Official learning objectives

### LO3.1

Deploy intelligent risk assessment for citizen developer applications
based on data sensitivity.

### LO3.2

Implement automated approval workflows with escalation for high-risk
applications.

### LO3.3

Configure governance dashboards and risk analytics for executive oversight.

## 2. LO3.1 — Intelligent risk assessment

### Implementation

The deterministic-v2 risk engine evaluates governed data classification,
registration, ownership, business purpose, internet exposure, external
integrations, integration approval and credential type.

ML anomaly detection and classification suggestions influence governance
review requirements but do not replace deterministic scoring or mandatory
policy enforcement.

### Live sensitivity-dependent risk verification

| Scenario | Score | Level |
|---|---:|---|
| Public | 0 | Low |
| Internal | 0 | Low |
| Unknown classification | 10 | Low |
| Confidential | 20 | Low |
| Restricted | 25 | Medium |
| Restricted with additional exposure and integration risks | 80 | Critical |

All six live risk-engine scenarios passed.
Risk factors were returned with explainable scoring results.

### Persisted governance evidence

| Application | Score | Outcome | Decision ID |
|---|---:|---|---|
| Objective 1 Shadow IT AI Proof | 85 | SECURITY_REVIEW | 75880177-8ab2-489a-bf5d-66840fce615e |
| LO1 ML Cold Start Proof | 45 | SECURITY_REVIEW | d8effdfc-7a0f-4986-a1cd-17e81f9bd4d7 |
| LO2 Isolated Publish Fixture | 0 | SECURITY_REVIEW | 45d6b20a-c303-42eb-bb17-36f288d01cfc |
| LO2 Publish Allow Fixture | 0 | SECURITY_REVIEW | 83de59e0-8de2-4b95-8771-af169b16f5c3 |

Persisted decision reasons demonstrate anomaly-based review,
classification-advisory review and incomplete-evidence review.

The two low-risk LO2 fixtures demonstrate that advisory classification
can require Security/GRC review without changing the numerical risk score
or authoritative classification.

### Safeguards

- Mandatory OPA denial takes precedence over AI results.
- Incomplete automatic governance evidence requires review when policy allows.
- Expired Appsmith observations prevent fresh automatic decisions.
- OPA failure prevents generation of a new automatic approval.
- Classification changes invalidate previously applicable review decisions.

### Acceptance

VERIFIED within the scoped MVP and observed Appsmith governance workflow.

The live risk-engine scenarios are service-level tests. AI-assisted routing
is supported by persisted historical decisions and integration regression
evidence. Identical evidence safeguards across every manual entry point
and every LCNC platform are not established.

## 3. LO3.2 — Automated approvals and escalation

### Routing configuration

| Outcome | Initial role | SLA |
|---|---|---|
| AUTO_APPROVE | Business Application Owner | 24 hours |
| BUSINESS_REVIEW | Business Application Owner | 24 hours |
| SECURITY_REVIEW | Security/GRC Reviewer | 8 hours |
| BLOCK | Security/GRC Reviewer | 4 hours |

AUTO_APPROVE denotes automated governance clearance followed by a
human-confirmation request. It does not imply unrestricted publication.

### Regression evidence

The isolated PostgreSQL integration suite verifies:

- Automatic low-risk governance clearance and confirmation routing.
- High-risk security review.
- Escalation after the configured review deadline.
- Senior Security/GRC reviewer authority.
- Rejection of ordinary reviewers for senior review decisions.
- Persistence of verified reviewer identity and policy.
- Prevention of duplicate routing and escalation events.
- Mandatory training enforcement.
- Rejection of attempts to approve a mandatory policy BLOCK.
- Concurrent request handling and expired evidence rejection.
- Routing, policy and training outage handling.

The reviewer tests exercise actual reviewer-validation logic using
controlled Vault lookup fixtures rather than operational credentials.

### Historical operational escalation evidence

Ten retrieved high-risk or critical-risk escalation events occurred
at or after their recorded SLA deadlines.

Representative record:

- Application: LO1 Connector Proof 20261116T083033Z
- Risk score: 60
- Risk level: high
- Governance outcome: SECURITY_REVIEW
- Approval ID: 83091dde-18b9-4f79-b608-e355d833e3c4
- SLA deadline: 2026-11-19T09:54:40.164164+00:00
- Escalation event: 2026-11-19T10:27:23.735766+00:00
- Previous role: Security/GRC Reviewer
- Escalated role: Senior Security/GRC Reviewer
- Escalation level: 1
- Reason: Approval SLA expired.

Historical automatic approval evidence:

- Application: Expense approval
- Decision ID: d0dfc10f-939c-45a6-9b23-c84a02269730
- Risk score: 0
- Governance status: completed
- Approval route: human_confirmation
- Historical approval status: superseded

Authenticated ordinary-reviewer acceptance from LO2 is reused where
applicable. See CR-002-LO2-compliance-acceptance.md.

### Acceptance

VERIFIED within the scoped MVP.

Senior reviewer decision authorization was demonstrated in the isolated
integration environment. Historical operational escalation events prove
escalation functionality, but consistent escalation processing latency
and all reviewer assignment variants are not certified.

## 4. LO3.3 — Executive governance dashboards

### Identified gap

The original portal provided individual application evidence and a
limited portfolio summary.

Grafana displayed operational event counters rather than current
distinct-application risk distributions.

The approval listing returned 50 records despite 66 persisted requests.

### Implemented remediation

- Read-only GET /executive-summary in Governance Automation.
- Exact portal proxy route GET /api/executive-summary.
- One PostgreSQL statement snapshot for aggregate metrics.
- Executive Governance Overview in the existing portal.
- Assessed risk distribution and assessment coverage.
- Separate stale and unassessed risk indicators.
- Governance status and outcome distributions.
- Recorded open requests, overdue pending requests and escalation counts.
- Complete approval record aggregation without listing truncation.
- Explicit distinction between recorded open requests and review eligibility.
- Snapshot timestamp and unavailable-data handling.

Existing Grafana operational monitoring was retained.

No new microservice, dependency, database table or migration was required.

### Live reconciliation

Database snapshot: 2026-11-21T08:55:39.407004+00:00

Both the direct executive API and the portal-proxied API returned
HTTP 200 and matched independently aggregated PostgreSQL records.

| Metric | Verified value |
|---|---:|
| Applications | 21 |
| Assessed | 18 |
| Assessment coverage | 85.7% |
| Stale risk | 0 |
| Not assessed | 3 |
| Critical risk | 1 |
| High risk | 8 |
| Medium risk | 5 |
| Low risk | 4 |
| Pending governance review | 13 |
| Blocked | 4 |
| Stale governance | 1 |
| Not evaluated | 3 |
| Total approval records | 66 |
| Pending approval requests | 0 |
| Escalated approval requests | 16 |
| Pending overdue requests | 0 |
| Approved | 4 |
| Changes requested | 1 |
| Rejected | 0 |
| Superseded | 45 |

### Browser visual acceptance

Browser: Safari
Environment: Local Governance Portal
Displayed database snapshot: 2026-11-21T08:58:06.306248+00:00

Five user-provided browser screenshots confirmed rendering of:

- Portfolio summary and risk assessment coverage.
- Assessed risk severity distribution.
- Governance status and outcome distribution.
- Open approval requests and escalations.
- Complete approval record history.
- Existing application inventory.
- Metric scope and evidence limitation explanations.

Displayed values matched the earlier independently verified API and
database snapshot.

The screenshots are retained in the acceptance conversation and are
not embedded in this repository record.

### Acceptance

VERIFIED for the deployed MVP executive overview.

The dashboard represents persisted application and approval states,
including historical demonstration fixtures. It is not a certified
production portfolio, continuous real-time risk feed or independent
assurance of review eligibility.

## 5. Final regression verification

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Automatic governance PostgreSQL integration | 24 | 0 | 0 |
| Risk engine, AI routing and risk connection lifecycle | 9 | 0 | 0 |
| Total | 33 | 0 | 0 |

Test files:

- tests/test_automatic_governance_handoff.py
- tests/test_risk_engine.py
- tests/test_ai_governance_escalation.py
- tests/test_lo2_risk_connection_lifecycle.py

The existing integration harness was updated for migration 027 and
authenticated reviewer validation. Three additional regressions cover
automatic low-risk approval, high-risk SLA escalation and executive analytics.

These are focused acceptance results, not a claim that the entire
repository test suite was executed during LO3.

## 6. Deployment and operational integrity

Only Governance Automation and Governance Portal were rebuilt and redeployed.

- Nginx configuration validation passed.
- Direct executive summary endpoint returned HTTP 200.
- Portal executive summary endpoint returned HTTP 200.
- Deployed HTML and JavaScript assets were verified.
- All ten inspected operational services were healthy.
- Existing Discovery and Governance API replicas remained running.
- No operational database records were manually changed during LO3.
- No operational schema migrations or credential changes were required.
- Final git diff integrity check passed.

## 7. Final disposition

| Objective | Scoped acceptance |
|---|---|
| LO3.1 — Intelligent risk assessment | VERIFIED |
| LO3.2 — Automated approvals and escalation | VERIFIED |
| LO3.3 — Executive dashboards and risk analytics | VERIFIED |

Accept the three LO3 requirements within the demonstrated MVP scope.
Retain documented platform, latency, evidence freshness, reviewer assignment
and production assurance limitations.

No further LO3 implementation is required for this scoped acceptance.

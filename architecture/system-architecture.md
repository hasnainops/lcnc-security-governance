# LCNC Security Governance — MVP V3 System Architecture

## Purpose

The platform provides an external AI-assisted security and governance control plane for enterprise low-code/no-code environments.

Appsmith remains the connected reference LCNC platform. MVP V3 also introduces an Enterprise Discovery service that accepts normalized discovery events from multiple source adapters, persists source evidence, and hands sufficiently complete telemetry to ML analysis.

The control plane discovers and inventories citizen-developed applications, analyzes risk, applies security controls, enforces policy, automates accountable approval workflows, manages time-limited privileged access, records evidence, and provides governance and developer guidance.

## Core Design Principles

- Unknown telemetry is not treated as safe.
- AI assists detection and classification but does not independently authorize applications.
- OPA makes mandatory policy and access-control decisions.
- DLP inspects sensitive data before external transfers.
- Historical evidence is retained after reassessment.
- Material application changes make previous security state stale.
- Automation supports human accountability rather than replacing it.
- Hard policy blocks cannot be silently overridden by human approval.
- Privileged access is time-limited and auditable through JIT grants.
- Governance API database credentials are issued dynamically through Vault.
- Internal services remain internal unless host access is required.
- Security controls have distinct responsibilities rather than stacking overlapping tools.

## High-Level Architecture

Citizen Developer
|
v
Appsmith / Enterprise Discovery Sources
|
+----> Appsmith Discovery Worker
|
+----> Enterprise Discovery
|       - normalized source events
|       - durable discovery evidence
|       - ML handoff
|
v
ML Analytics
|       - Isolation Forest anomaly detection
|       - TF-IDF + Logistic Regression classification
|
v
Governance API
|
+----> Risk Engine
|
+----> Security Scanner
|
+----> OPA
|       - governance policy
|       - fine-grained access policy
|       - JIT-aware access decisions
|
+----> Governance Automation
|       - approval routing
|       - SLA escalation
|       - human decisions
|       - training gate
|       - JIT privilege lifecycle
|
+----> Integration Gateway
|          |
|          v
|       DLP Engine
|
+----> Dynamic Compliance
|
+----> Citizen Guidance / Training Automation
|
+----> Vault
|       - AppRole authentication
|       - dynamic PostgreSQL credentials
|
v
PostgreSQL Evidence Store
|
+----> Governance Portal
|
+----> Prometheus / Grafana

DevSecOps controls include pytest, OPA tests, SonarQube static
analysis and Quality Gate, Trivy vulnerability/secret/misconfiguration
scanning, OWASP ZAP baseline DAST configuration, and Dependabot.

## 1. Citizen Development Layer

Reference platform:

- Appsmith

Responsibilities:

- hosts citizen-developed applications
- exposes application metadata
- provides the source inventory for discovery

Appsmith does not make governance decisions.

## 2. Continuous and Enterprise Discovery Layer

Components:

- `discovery`
- `enterprise-discovery`

### Appsmith Discovery

The Appsmith discovery worker:

- authenticates to the connected Appsmith platform
- enumerates applications every 60 seconds
- compares discovered applications with the governance inventory
- identifies previously unknown applications
- refreshes last-seen evidence
- triggers downstream analysis when required metadata exists

### Enterprise Discovery

The Enterprise Discovery service:

- accepts normalized discovery events from source adapters
- records source type and external source identifier
- persists discovery evidence in `enterprise_discoveries`
- supports generic enterprise security-feed ingestion
- exposes a source registry for additional enterprise connectors
- invokes ML analysis automatically when telemetry is feature-complete

Appsmith is the connected reference implementation.

The generic enterprise feed demonstrates the multi-source ingestion contract.

A Microsoft Defender Cloud Apps adapter is represented as an extension point but is not configured as a live production connector.

Missing telemetry remains pending rather than being treated as safe.

Examples:

- `ML-PENDING`
- `CLASSIFICATION-PENDING`
- `SCAN-PENDING`

## 3. AI / ML Analytics Layer

Component:

- `ml-analytics`

### Shadow IT Anomaly Detection

Model:

- Isolation Forest
- `isolation-forest-v1`

Example features:

- owner known
- business purpose known
- internet exposure
- external integration count
- unapproved integration count
- API-key usage
- connector count
- external domain count
- recent change activity

Outputs:

- anomaly decision
- anomaly score
- context signals
- immutable assessment evidence

### AI-Assisted Classification

Model:

- TF-IDF
- Logistic Regression
- `classification-v1`

Classes:

- public
- internal
- confidential
- restricted

Inputs include:

- application name
- business purpose
- data fields
- connector metadata

Outputs include:

- suggested classification
- confidence
- review-required state

AI classification is advisory. The stored governance classification remains authoritative.

## 4. Governance Control Plane

Primary component:

- `governance-api`

Automation component:

- `governance-automation`

Governance API responsibilities:

- application inventory
- metadata enrichment
- enterprise discovery integration
- ML orchestration
- security-scan orchestration
- risk assessment
- governance evaluation
- access authorization
- outbound-transfer evaluation
- dynamic compliance
- audit history
- citizen-developer guidance
- training automation

Governance Automation responsibilities:

- create persistent approval requests
- route cases to the required accountable role
- enforce approval SLA deadlines
- escalate overdue approval requests
- persist human approval decisions and reasons
- prevent human approval from overriding a mandatory BLOCK
- enforce required-training gates
- manage JIT privilege requests
- issue time-limited privilege grants after accountable approval
- expire or revoke privilege grants
- persist approval and privilege lifecycle events

Governance evaluation automatically hands actionable workflow outcomes from the Governance API to Governance Automation.

## 5. Risk Engine

Component:

- `risk-engine`

Provides:

- deterministic risk scoring
- explainable factors
- risk levels
- model/version evidence

Risk scores are advisory inputs and cannot override mandatory policy.

## 6. Citizen Application Security Scanner

Component:

- `security-scanner`

Checks include:

- unregistered application
- missing owner
- unknown classification
- unapproved external integration
- API-key usage
- insecure HTTP integration
- possible embedded secret
- sensitive data with external connectivity

Outputs include:

- findings
- severity
- pass/fail state
- historical scan evidence

## 7. Policy-as-Code, Access Control, and JIT Privilege

Component:

- OPA

Policy domains:

- `lcnc.governance`
- `lcnc.access`

OPA evaluates underlying facts rather than relying only on numerical risk.

Access policy considers:

- user role
- requested action
- application registration
- data sensitivity
- valid JIT privilege context

Permanent role permissions and temporary JIT grants remain subject to mandatory policy guardrails.

JIT access does not bypass:

- application registration requirements
- restricted-data protections
- mandatory governance policy

JIT lifecycle:

Request
→ accountable Security/GRC decision
→ time-limited grant
→ OPA-aware authorization
→ automatic expiry or explicit revocation

Access and privilege lifecycle decisions are persisted for audit.

## 8. DLP and Outbound Transfer Enforcement

Components:

- `dlp-engine`
- `integration-gateway`

DLP detects indicators including:

- email
- phone
- payment card
- SSN
- confidential field names
- restricted field names

Raw sensitive values are not persisted as evidence.

The Integration Gateway combines:

- authoritative classification
- DLP-detected sensitivity
- destination trust
- transport security

Examples of blocked transfers:

- unknown classification to an external destination
- unapproved external destination
- external HTTP destination
- restricted data leaving the approved boundary

## 9. Dynamic Compliance

Seven live controls are evaluated:

- CTRL-01 Owner assigned
- CTRL-02 Classification established
- CTRL-03 External integrations approved
- CTRL-04 Security scanning acceptable
- CTRL-05 Sensitive egress protected by DLP
- CTRL-06 Access decisions enforced through OPA
- CTRL-07 Governance decision current

Statuses:

- pass
- fail
- not assessed

Compliance snapshots can be stored as historical evidence.

Framework references are alignment themes, not certification claims.

## 10. Citizen Developer Enablement

Capabilities:

- evidence-based security score
- Gold / Silver / Bronze / Needs Attention badge
- targeted secure-development guidance
- recommended training
- automatic training assignment
- control-to-training mapping
- due dates for required training
- training completion tracking
- approval gating when required training remains incomplete
- achievement status
- durable training lifecycle events

Training requirements are triggered by actual failed or not-assessed controls.

Training readiness can affect approval workflow progression, but completion of training does not override a mandatory OPA BLOCK.

## 11. Evidence Layer

Primary durable component:

- PostgreSQL

Stored evidence includes:

- applications
- discovery state
- enterprise discovery records
- risk assessments
- anomaly assessments
- classification assessments
- security scans and findings
- policy decisions
- governance decisions
- approval requests
- approval events
- OPA access decisions
- JIT privilege requests
- JIT privilege grants
- JIT privilege events
- integration transfer events
- compliance assessments
- training completions
- training assignments
- training events

Additional runtime evidence exists in:

- Vault for dynamic credential issuance
- Prometheus for operational metrics
- Grafana for visualization
- SonarQube for static-analysis and Quality Gate evidence
- Git/GitHub for source and CI traceability

## 12. Governance Portal

Component:

- `governance-portal`

Provides visibility into:

- application inventory
- ownership and registration
- risk
- AI anomaly evidence
- AI classification
- security scanning
- DLP / transfer decisions
- OPA access decisions
- dynamic compliance
- security score and badge
- targeted citizen-developer guidance
- historical governance evidence

The browser accesses the Governance API through the Nginx `/api/` reverse proxy.

## 13. Observability

Components:

- Prometheus
- Grafana

Provides visibility into:

- service health
- governance activity
- risk activity
- policy outcomes
- workflow behavior
- operational metrics

## 14. DevSecOps

The project intentionally uses distinct controls rather than overlapping scanners.

Validation responsibilities:

- pytest — application and security regression testing
- OPA tests — governance and access-policy validation
- SonarQube — static source analysis, maintainability, security findings, and Quality Gate
- Trivy — vulnerability, secret, and misconfiguration scanning
- OWASP ZAP — baseline runtime DAST workflow
- Dependabot — dependency and container update lifecycle
- Docker Compose validation — deployment configuration validation

SonarQube replaces CodeQL as the project's source-code static-analysis platform.

The local SonarQube instance is available at `localhost:9000`.

The ZAP GitHub workflow is configured, but execution evidence should only be claimed when the workflow has actually run.

Runtime credentials are kept outside Git.

`.env` is excluded from Git.

Governance API database access does not use a long-lived application database password. It authenticates to Vault using AppRole and requests dynamic PostgreSQL credentials.

## Decision Authority Model

| Component | Responsibility |
|---|---|
| ML Analytics | Detect and classify |
| Risk Engine | Quantify and explain risk |
| Security Scanner | Detect deterministic findings |
| DLP | Inspect sensitive data |
| Integration Gateway | Enforce outbound-transfer controls |
| OPA | Mandatory governance and access decisions |
| Governance Workflow | Approval and escalation |
| Human Stakeholders | Final organizational accountability |

## Failure Behavior

### ML unavailable

AI analysis remains unavailable or pending. A safe result is not fabricated.

### Scanner unavailable

The application is not treated as having passed security scanning.

### Risk Engine unavailable

Governance evaluation fails instead of inventing a risk result.

### OPA unavailable

Mandatory authorization fails closed.

### DLP unavailable

Outbound-transfer evaluation fails closed and blocks the transfer.

### Missing telemetry

Missing values remain unknown or pending rather than being converted to safe defaults.

## Local MVP Deployment

Host-accessible services:

- Governance Portal — `localhost:3000`
- Grafana — `localhost:3001`
- Governance API — `localhost:8000`
- ML Analytics — `localhost:8002`
- DLP Engine — `localhost:8004`
- Enterprise Discovery — `localhost:8006`
- Governance Automation — `localhost:8007`
- Appsmith — `localhost:8080`
- OPA — `localhost:8181`
- Vault — `localhost:8200`
- SonarQube — `localhost:9000`
- Prometheus — `localhost:9090`

Internal-only services:

- Risk Engine — `8001`
- Security Scanner — `8003`
- Integration Gateway — `8005`
- PostgreSQL — `5432`
- Appsmith discovery worker — background service

Docker Compose provides the local service network.

Internal-only services are intentionally not exposed to the host when direct browser/operator access is unnecessary.

## Production Boundary

The current implementation is a localhost-focused interview/capstone MVP.

Production hardening would additionally require:

- enterprise SSO and MFA
- stronger API authentication
- workload/service identities
- TLS or mTLS between services
- production-hardened Vault deployment
- persistent Vault storage and HA
- operational Vault unseal/recovery procedures
- migration of remaining local demo secrets into managed secret paths
- network segmentation
- database hardening and encryption
- tamper-evident audit storage
- high availability
- backup and disaster recovery
- SIEM integration
- additional production LCNC/security connectors
- distributed rate limiting
- signed artifacts and software provenance
- production model monitoring and validation

These are future production requirements and are not claimed as current MVP capabilities.

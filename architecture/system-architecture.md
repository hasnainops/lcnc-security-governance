# LCNC Security Governance — MVP V2 System Architecture

## Purpose

The platform provides an external AI-assisted security and governance control plane for enterprise low-code/no-code environments.

Appsmith is the reference LCNC platform. The control plane discovers citizen-developed applications, analyzes risk, applies security controls, enforces policy, records evidence, and provides governance and developer guidance.

## Core Design Principles

- Unknown telemetry is not treated as safe.
- AI assists detection and classification but does not independently authorize applications.
- OPA makes mandatory policy and access-control decisions.
- DLP inspects sensitive data before external transfers.
- Historical evidence is retained after reassessment.
- Material application changes make previous security state stale.
- Automation supports human accountability.
- Internal services remain internal unless host access is required.

## High-Level Architecture

Citizen Developer
    |
    v
Appsmith LCNC Platform
    |
    v
Continuous Discovery
    |
    +----> ML Analytics
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
    |       - Governance policy
    |       - Fine-grained access policy
    |
    +----> Integration Gateway
    |          |
    |          v
    |       DLP Engine
    |
    +----> Dynamic Compliance
    |
    +----> Citizen Guidance / Training
    |
    v
PostgreSQL Evidence Store
    |
    +----> Governance Portal
    |
    +----> Prometheus / Grafana

GitHub Actions validates tests, OPA policies, dependencies, secrets,
container configuration, and vulnerability findings.

## 1. Citizen Development Layer

Reference platform:

- Appsmith

Responsibilities:

- hosts citizen-developed applications
- exposes application metadata
- provides the source inventory for discovery

Appsmith does not make governance decisions.

## 2. Continuous Discovery Layer

Component:

- `discovery`

Capabilities:

- authenticates to Appsmith
- enumerates applications every 60 seconds
- compares discovered applications with the governance inventory
- identifies previously unknown applications
- refreshes last-seen evidence
- triggers ML and scanning when required metadata exists

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

Component:

- `governance-api`

Responsibilities:

- application inventory
- metadata enrichment
- ML orchestration
- security-scan orchestration
- risk assessment
- governance evaluation
- access authorization
- outbound-transfer evaluation
- dynamic compliance
- audit history
- citizen-developer guidance
- training completion tracking

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

## 7. Policy-as-Code and Access Control

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

OPA decisions are persisted for audit.

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
- training completion tracking
- achievement status

Training recommendations are triggered by actual failed or not-assessed controls.

## 11. Evidence Layer

Component:

- PostgreSQL

Stored evidence includes:

- applications
- discovery state
- risk assessments
- anomaly assessments
- classification assessments
- security scans and findings
- policy decisions
- governance decisions
- OPA access decisions
- integration transfer events
- compliance assessments
- training completions

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

GitHub Actions provides automated validation for:

- Python tests
- ML tests
- scanner tests
- DLP/gateway tests
- OPA policy tests
- Docker Compose validation
- Trivy security scanning
- HIGH/CRITICAL vulnerability gates
- secret scanning
- dependency updates with Dependabot

Runtime credentials are supplied through environment variables.

`.env` is excluded from Git.

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

- Appsmith — `localhost:8080`
- Governance API — `localhost:8000`
- Governance Portal — `localhost:3000`
- Grafana — `localhost:3001`
- Prometheus — `localhost:9090`
- OPA — `localhost:8181`

Internal services:

- Risk Engine — `8001`
- ML Analytics — `8002`
- Security Scanner — `8003`
- DLP Engine — `8004`
- Integration Gateway — `8005`
- PostgreSQL — `5432`

Docker Compose provides the local service network.

## Production Boundary

The current implementation is a localhost-focused interview/capstone MVP.

Production hardening would additionally require:

- enterprise SSO
- stronger API authentication
- service identities
- TLS between services
- centralized secrets management
- network segmentation
- database hardening and encryption
- tamper-evident audit storage
- high availability
- backup and disaster recovery
- SIEM integration
- additional LCNC connectors
- distributed rate limiting
- signed artifacts and software provenance

These are future production requirements and are not claimed as current MVP capabilities.

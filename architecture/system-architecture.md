# LCNC Security Governance System Architecture

## Objective

Provide an external governance and security control plane for enterprise low-code/no-code environments without rebuilding the LCNC platform itself.

Appsmith is the reference LCNC implementation. The governance architecture remains platform-agnostic through adapter-based discovery.

## Architecture Layers

### 1. Citizen Development Layer

Reference platform:

- Appsmith

Responsibilities:

- citizen-developed applications
- application metadata
- LCNC application lifecycle

Appsmith does not make governance decisions.

### 2. Discovery Layer

The Appsmith discovery adapter:

- authenticates to the LCNC platform
- enumerates applications
- compares applications against the governance inventory
- detects previously unknown applications
- updates last-seen evidence

Unknown applications enter governance as unregistered rather than trusted.

### 3. Governance Control Plane

The Governance API orchestrates:

- application inventory
- metadata enrichment
- risk assessment
- policy evaluation
- governance workflow
- compliance evidence
- audit history

It is the primary coordination layer.

### 4. Risk Assessment Layer

The Risk Engine provides:

- deterministic scoring
- explainable weighted factors
- risk levels
- model versioning

Risk scores are advisory governance inputs.

They do not independently authorize applications.

### 5. Policy Enforcement Layer

OPA provides deterministic hard-policy enforcement.

Example:

Confidential or restricted information using an unapproved external integration results in DENY.

OPA evaluates underlying facts independently of the numerical risk score.

### 6. Governance Workflow Layer

The workflow converts risk and policy evidence into:

- AUTO_APPROVE
- BUSINESS_REVIEW
- SECURITY_REVIEW
- BLOCK

Human accountability is preserved through required governance roles.

### 7. Evidence Layer

PostgreSQL persists:

- application inventory
- discovery timestamps
- risk assessments
- policy decisions
- governance decisions

Historical decisions are retained after remediation and reassessment.

### 8. Governance Experience

The Governance Portal provides:

- application inventory
- risk state
- governance status
- historical decisions
- control evidence
- NIST / ISO / OWASP alignment

### 9. Observability Layer

Prometheus and Grafana provide:

- control-plane health
- risk activity
- policy outcomes
- governance outcomes
- workflow latency
- service availability

### 10. DevSecOps Layer

GitHub Actions provides automated validation for:

- Python syntax
- deterministic risk tests
- dependency failure tests
- OPA validation
- OPA policy tests
- Docker Compose configuration
- Trivy HIGH/CRITICAL security findings

Custom services run as non-root.

## Primary Governance Flow

Citizen Developer
    |
    v
LCNC Platform
    |
    v
Discovery Adapter
    |
    v
Application Inventory
    |
    v
Risk Engine
    |
    +---- Explainable Risk Evidence
    |
    v
OPA Policy Engine
    |
    +---- Hard ALLOW / DENY
    |
    v
Governance Workflow
    |
    +---- AUTO_APPROVE
    +---- BUSINESS_REVIEW
    +---- SECURITY_REVIEW
    +---- BLOCK
    |
    v
PostgreSQL Audit Evidence
    |
    +---- Governance Portal
    +---- Compliance Evidence
    +---- Prometheus / Grafana

## Demo Scenario

### Initial Discovery

Customer Data Export appears in Appsmith but is outside the governance inventory.

Discovery identifies it as shadow IT and registers it as:

- unregistered
- owner unknown
- classification unknown
- integration status unknown

### Risk Enrichment

The application is identified as:

- confidential
- externally integrated
- integration not approved
- API-key credential
- no accountable owner

Risk becomes CRITICAL.

### Hard Policy

OPA independently evaluates the facts.

Confidential data plus an unapproved external integration produces:

DENY

### Governance Result

The orchestration layer returns:

BLOCK

Required role:

Security/GRC Reviewer

The complete evidence chain is persisted.

### Remediation

The organization:

- registers the application
- assigns an owner
- records its business purpose
- removes the unapproved external integration
- removes the API-key dependency
- reassesses the application

The result becomes:

- LOW risk
- OPA ALLOW
- AUTO_APPROVE

The previous BLOCK decision remains available as audit evidence.

## Failure Behavior

If the Risk Engine is unavailable:

- governance evaluation returns 503
- no policy decision is created
- no governance approval is created

If OPA is unavailable:

- risk assessment may complete
- governance evaluation returns 503
- no policy authorization is fabricated
- no governance approval is created

The system therefore fails closed at mandatory governance decision points.

## Production Boundary

The MVP is intentionally localhost-focused.

A production implementation would additionally require:

- enterprise SSO
- RBAC
- service identity
- TLS
- centralized secrets management
- network segmentation
- immutable or tamper-evident audit storage
- HA and disaster recovery
- scheduled/event-driven discovery
- SIEM integration
- enterprise LCNC connectors

These are production requirements rather than capabilities claimed by the current MVP.

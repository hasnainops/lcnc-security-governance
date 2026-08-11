# LCNC Security Governance Threat Model

## Purpose

This threat model identifies security risks across the LCNC Security Governance control plane.

The objective is not to claim that every threat is completely eliminated. The objective is to make trust boundaries, implemented controls, residual risks, and future security requirements explicit.

## Security Principles

The MVP follows these principles:

- unknown does not equal safe
- risk scoring is explainable and deterministic
- hard policy enforcement is separated from risk scoring
- material application changes invalidate previous governance decisions
- governance evidence is persisted rather than overwritten
- sensitive internal services are not exposed publicly
- custom containers run as non-root
- security checks are enforced in CI
- automation supports human accountability rather than replacing it

## Critical Assets

The primary assets are:

1. Application inventory
2. Application ownership and classification metadata
3. Appsmith discovery credentials
4. Risk-assessment logic
5. OPA governance policies
6. Governance decisions
7. Audit history
8. PostgreSQL data
9. Governance API
10. Governance Portal
11. Prometheus and Grafana telemetry
12. Source code and CI/CD pipeline

## Trust Boundaries

### Boundary 1: Citizen Developer Platform

Appsmith is outside the governance decision engine.

The discovery adapter authenticates to Appsmith and retrieves application metadata.

Trust assumption:

- Appsmith identity and metadata are accepted as discovery inputs.
- Appsmith itself is not trusted to make governance decisions.

### Boundary 2: Discovery to Governance API

The discovery service submits newly identified applications and refreshes known application records.

Security concern:

A compromised discovery adapter could provide incorrect inventory information.

### Boundary 3: Governance API to Risk Engine

The Governance API sends normalized application facts to the deterministic risk engine.

The risk engine returns:

- score
- risk level
- contributing factors
- model version

Risk scores are advisory inputs to governance workflow logic.

### Boundary 4: Governance API to OPA

OPA is the hard-policy decision point.

OPA evaluates facts independently from the numerical risk score.

Example:

Confidential or restricted data using an unapproved external integration results in DENY.

This prevents a low or manipulated numerical score from bypassing a mandatory security rule.

### Boundary 5: Governance API to PostgreSQL

PostgreSQL stores:

- applications
- risk assessments
- policy decisions
- governance decisions
- discovery timestamps

Database integrity is therefore critical to governance evidence.

### Boundary 6: Browser to Governance Portal

The Governance Portal displays governance evidence and invokes Governance API operations through the Nginx reverse proxy.

The current MVP is localhost-only.

Enterprise authentication and authorization are outside the current MVP and are identified as a production requirement.

### Boundary 7: Source Repository and CI/CD

GitHub contains:

- application code
- Dockerfiles
- OPA policy
- risk-engine tests
- security-validation workflow
- compliance mappings

Changes entering the main branch are subject to automated security validation.

---

## Threat Scenarios

| ID | Threat | Potential Impact | Current Mitigation | Residual Risk | Status |
|---|---|---|---|---|---|
| TM-01 | Unauthorized access to Governance Portal or API | Unauthorized assessment or governance actions | Services bound to localhost; internal services not publicly exposed | No enterprise SSO/RBAC in MVP | Partial |
| TM-02 | Discovery credential compromise | Unauthorized access to LCNC inventory | Credentials stored outside Git in `.env`; secret scanning in CI | Local environment secrets still require operational protection and rotation | Partial |
| TM-03 | Incorrect or forged discovery metadata | Incorrect inventory and governance decisions | Authenticated Appsmith adapter; unique external application IDs; persisted discovery timestamps | Source-platform metadata can still be inaccurate or compromised | Partial |
| TM-04 | Governance workflow bypass | Risky application receives approval without mandatory policy evaluation | Governance orchestration invokes risk assessment and OPA before decision | Direct API authorization controls are not implemented | Partial |
| TM-05 | OPA policy tampering | Mandatory security guardrails weakened | Policy stored in Git; OPA tests; CI validation; policy mounted read-only at runtime | Repository write access remains a privileged trust boundary | Implemented / Residual |
| TM-06 | Risk-model manipulation | Artificially reduced application risk score | Deterministic model; explainable factors; model version stored; automated tests | Repository compromise could modify scoring logic | Implemented / Residual |
| TM-07 | Stale approval after application changes | Previously approved application remains trusted after risk increases | Material metadata updates mark risk and governance state stale and require reassessment | Correct detection depends on visibility of the change | Implemented |
| TM-08 | Audit-history modification | Loss of trustworthy governance evidence | Historical risk, policy, and governance records are persisted separately | Database is not append-only or cryptographically tamper-evident | Partial |
| TM-09 | Sensitive-data exfiltration through external integration | Confidential or restricted data leaves approved boundary | OPA blocks confidential/restricted data with unapproved external integration | Policy decision does not itself enforce network-layer egress | Partial |
| TM-10 | Shadow application evades discovery | Unmanaged LCNC application remains outside governance | Authenticated inventory discovery and known-vs-shadow comparison | Discovery is not yet continuous or event-driven | Partial |
| TM-11 | Governance service denial of service | Assessments and approvals unavailable | Docker restart policies, health checks, Prometheus monitoring | No HA, rate limiting, clustering, or failover in local MVP | Partial |
| TM-12 | Vulnerable or insecure container configuration | Control-plane compromise | Trivy HIGH/CRITICAL CI gate; non-root custom containers; minimal images | Base-image and dependency vulnerabilities require continuous maintenance | Implemented / Continuous |
| TM-13 | Monitoring data exposure | Operational information disclosed | Prometheus/Grafana bound to localhost | Production deployment requires authentication and network segmentation | Partial |
| TM-14 | Secret committed to source control | Credential disclosure | `.env` excluded from Git; Trivy secret scanner in CI | Developers can still mishandle secrets outside automated coverage | Implemented / Residual |

---

## High-Risk Abuse Case

### Scenario

A citizen developer creates an application that processes confidential customer data and connects it to an unapproved external API.

### Attack / Risk Path

1. Application is created outside the governance inventory.
2. Discovery detects the application.
3. Application enters the inventory as unregistered.
4. Data classification is identified as confidential.
5. External integration is present.
6. Integration approval is false.
7. Risk engine calculates elevated risk.
8. OPA evaluates the underlying facts.
9. OPA returns DENY.
10. Governance workflow returns BLOCK.
11. Security/GRC Reviewer becomes the required role.
12. Decision and rationale are persisted.

### Important Design Decision

OPA does not rely only on the risk score.

The mandatory security decision uses the underlying application facts.

This reduces the risk that a scoring defect or changed weighting allows a mandatory security control to be bypassed.

---

## Remediation Path

For the demonstrated Customer Data Export application:

Initial state:

- unregistered
- no owner
- confidential data
- external integration
- integration not approved
- API-key credential

Result:

- CRITICAL risk
- OPA DENY
- BLOCK

Remediation:

- register application
- assign accountable owner
- assign business unit and purpose
- retain confidential classification
- remove external integration
- remove API-key dependency
- reassess

Result:

- LOW risk
- OPA ALLOW
- AUTO_APPROVE

Historical BLOCK evidence remains available after remediation.

---

## Production Security Requirements

The following controls are intentionally outside the current localhost MVP and would be required before enterprise production use:

- enterprise SSO
- RBAC and least-privilege authorization
- service-to-service authentication
- TLS between services
- centralized secrets management
- database encryption and restricted database roles
- append-only or tamper-evident audit storage
- network segmentation
- outbound egress enforcement
- API rate limiting
- high availability
- backup and disaster recovery
- continuous discovery scheduling
- additional LCNC platform connectors
- signed build artifacts and software provenance
- centralized security logging and SIEM integration

These are production hardening requirements, not hidden assumptions about the current MVP.

## Residual Risk

The control plane reduces governance risk but cannot independently guarantee that:

- every LCNC platform is connected
- source metadata is truthful
- sensitive data never leaves approved environments
- administrators cannot misuse privileged access
- organizational governance processes are followed outside the technical workflow

Those risks require a combination of people, process, and technology controls.

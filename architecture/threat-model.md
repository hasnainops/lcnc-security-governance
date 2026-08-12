# LCNC Security Governance — MVP V2 Threat Model

## Purpose

This threat model identifies security risks across the AI-assisted LCNC Security Governance control plane.

The objective is to document:

- trust boundaries
- critical assets
- implemented controls
- residual risk
- production requirements

The MVP does not claim that every threat is eliminated.

## Security Principles

- Unknown telemetry is not treated as safe.
- AI output is advisory and does not independently authorize applications.
- Mandatory governance and access decisions use OPA.
- DLP inspection is separated from AI classification.
- Sensitive outbound transfers are evaluated through the Integration Gateway.
- Material application changes invalidate stale assessments.
- Historical evidence is retained.
- Mandatory decision dependencies fail closed.
- Runtime secrets remain outside Git.
- Custom application containers run as non-root.
- CI validates security controls and dependencies.
- Human stakeholders retain organizational accountability.

## Critical Assets

1. LCNC application inventory
2. Ownership and business-purpose metadata
3. Data classifications
4. Appsmith discovery credentials
5. ML anomaly model and assessments
6. ML classification model and assessments
7. Risk scoring logic
8. Security scanner rules and findings
9. OPA governance policies
10. OPA access-control policies
11. DLP inspection logic
12. Integration Gateway decisions
13. Governance decisions
14. Dynamic compliance evidence
15. Training and citizen-developer guidance
16. PostgreSQL audit history
17. Governance API
18. Governance Portal
19. Prometheus / Grafana telemetry
20. Source code and CI/CD pipeline

## Trust Boundaries

### Boundary 1 — Citizen Development Platform

Appsmith is the source LCNC platform.

The control plane accepts Appsmith metadata as discovery input but does not trust Appsmith to make governance decisions.

### Boundary 2 — Discovery

The continuous discovery adapter authenticates to Appsmith and refreshes inventory every 60 seconds.

Unknown applications enter governance as unregistered.

Missing telemetry remains unknown or pending.

### Boundary 3 — AI / ML Analytics

ML Analytics receives normalized application metadata.

It performs:

- Isolation Forest anomaly detection
- TF-IDF + Logistic Regression classification

AI results are advisory and persisted separately from authoritative governance fields.

### Boundary 4 — Governance Control Plane

The Governance API coordinates:

- inventory
- ML
- risk
- security scanning
- policy
- access decisions
- transfer evaluation
- compliance
- developer guidance

Compromise of this layer could influence multiple downstream controls.

### Boundary 5 — Mandatory Policy Enforcement

OPA evaluates:

- governance rules
- fine-grained access rules

OPA decisions use underlying facts rather than relying only on risk scores or ML output.

### Boundary 6 — Sensitive Data / Egress Enforcement

The Integration Gateway and DLP Engine inspect outbound-transfer context.

DLP identifies sensitive content.

The gateway evaluates:

- authoritative classification
- detected sensitivity
- destination trust
- transport security

The gateway can allow or block transfer requests.

### Boundary 7 — Evidence Store

PostgreSQL stores current state and historical security evidence.

Database integrity is therefore critical to auditability.

### Boundary 8 — Browser / Governance Experience

The Governance Portal communicates with the Governance API through the Nginx `/api/` reverse proxy.

The MVP is localhost-focused and does not claim enterprise SSO.

### Boundary 9 — Observability

Prometheus and Grafana receive operational telemetry.

Monitoring data may reveal control-plane behavior and therefore requires protection in production.

### Boundary 10 — Software Supply Chain

GitHub and CI contain:

- source code
- OPA policies
- Dockerfiles
- ML training code
- tests
- security workflows

Changes are validated with automated security checks.

---

## Threat Scenarios

| ID | Threat | Potential Impact | Current Mitigation | Residual Risk | Status |
|---|---|---|---|---|---|
| TM-01 | Unauthorized access to portal/API | Unauthorized governance operations | Localhost binding; OPA access-control capability | No enterprise SSO or strong API identity | Partial |
| TM-02 | Discovery credential compromise | Unauthorized LCNC inventory access | `.env` excluded from Git; environment variables; CI secret scanning | Local secret storage still requires operational protection | Partial |
| TM-03 | Forged or incorrect source metadata | Incorrect governance decisions | Authenticated discovery; persisted evidence; unknown values remain unknown | Compromised source platform can still provide false metadata | Partial |
| TM-04 | Governance workflow bypass | Risky app receives improper approval | Risk + OPA governance evaluation; OPA fine-grained access policy; stale state invalidation | Enterprise user authentication is not implemented | Implemented / Residual |
| TM-05 | OPA policy tampering | Mandatory guardrails weakened | Policy in Git; read-only runtime mount; OPA tests; CI validation | Repository write access remains privileged | Implemented / Residual |
| TM-06 | Risk-model manipulation | Artificially low risk score | Deterministic explainable scoring; tests; versioned evidence | Repository compromise could modify scoring logic | Implemented / Residual |
| TM-07 | ML model manipulation or misleading output | Incorrect anomaly/classification recommendation | AI is advisory; authoritative classification remains governed; model versions persisted | Synthetic training does not establish production accuracy | Implemented / Residual |
| TM-08 | Stale approval after material change | Changed app remains trusted | Material changes mark ML, scan and governance state stale | Depends on discovery visibility of the change | Implemented / Residual |
| TM-09 | Sensitive-data exfiltration | Confidential/restricted data leaves approved boundary | DLP inspection + Integration Gateway enforcement; unapproved/restricted transfers blocked | Applications that bypass the governed gateway remain an enterprise integration risk | Implemented / Residual |
| TM-10 | Shadow application evades discovery | Unmanaged app remains outside governance | Continuous 60-second Appsmith discovery; known-vs-shadow comparison | Coverage currently limited to connected LCNC platforms | Implemented / Residual |
| TM-11 | Embedded secret in citizen app | Credential disclosure | Security-scanner rule for possible embedded credentials; CI repository secret scanning | Detection is not a full enterprise secrets platform | Partial |
| TM-12 | DLP unavailable | Sensitive transfer bypass | Integration Gateway fails closed when DLP is unavailable | Service outage blocks legitimate transfer activity | Implemented |
| TM-13 | OPA unavailable | Mandatory authorization bypass | Governance/access decisions fail closed | Availability dependency on OPA | Implemented |
| TM-14 | Vulnerable container/dependency | Control-plane compromise | Non-root containers; Trivy filesystem/image scanning; HIGH/CRITICAL gates; Dependabot | Continuous maintenance still required | Implemented / Continuous |
| TM-15 | Audit-history tampering | Loss of trustworthy evidence | Separate historical assessment records in PostgreSQL | Database is not cryptographically tamper-evident | Partial |
| TM-16 | Monitoring information disclosure | Operational/security information exposed | Prometheus/Grafana bound locally | Production requires authentication and segmentation | Partial |

---

## Primary Abuse Case

### Scenario

A citizen developer creates an application that handles confidential customer data and connects to an unapproved external service.

### Risk Path

1. Citizen developer creates the application in Appsmith.
2. Continuous discovery detects it.
3. Inventory comparison identifies its governance state.
4. ML anomaly analysis evaluates unusual characteristics.
5. ML classification suggests data sensitivity when sufficient metadata exists.
6. Security scanner identifies deterministic security findings.
7. Risk engine calculates explainable risk.
8. OPA evaluates mandatory governance policy.
9. Governance workflow determines approval, escalation, or block.
10. Dynamic compliance records failed and passed controls.
11. Citizen guidance recommends remediation and targeted training.
12. Evidence is persisted.

If the application attempts an outbound sensitive transfer:

1. Governance API obtains the authoritative classification.
2. Integration Gateway invokes DLP.
3. DLP identifies sensitive-data indicators.
4. Gateway combines sensitivity and destination trust.
5. Policy returns ALLOW or BLOCK.
6. Safe audit metadata is persisted.
7. Raw transfer content is not stored in the audit record.

---

## AI Threat Considerations

### Model leakage

Governance outcomes, known shadow labels and risk scores are excluded from anomaly-model input features.

This reduces direct decision leakage.

### False positives / false negatives

ML results are not treated as mandatory authorization.

OPA, scanner rules, DLP and governance workflow remain separate control mechanisms.

### Synthetic training data

Current ML validation uses synthetic datasets.

Reported model metrics demonstrate implementation behavior only.

They are not production-accuracy claims.

### AI overreach

The architecture intentionally uses:

- ML for detection/classification
- deterministic controls for enforcement
- humans for accountable governance

---

## Fail-Closed Behavior

### OPA unavailable

Mandatory policy authorization is not fabricated.

### DLP unavailable

Outbound transfer evaluation blocks rather than bypassing inspection.

### Risk Engine unavailable

Governance evaluation does not invent a risk result.

### Missing telemetry

Unknown information remains unknown or pending.

### Scanner incomplete

Missing scanner evidence is not treated as a clean scan.

---

## Secure Credential Handling

Current MVP controls:

- `.env` excluded from Git
- runtime credentials supplied through environment variables
- `.env.example` contains placeholders
- Compose references environment variables
- CI performs secret scanning

Current limitation:

- no centralized enterprise secrets manager

---

## Residual Risk

The platform cannot independently guarantee that:

- every enterprise LCNC platform is connected
- source-platform metadata is truthful
- every network path is forced through the Integration Gateway
- administrators cannot misuse privileged host/database access
- all security findings are detectable from available metadata
- synthetic ML performance represents production accuracy
- organizational controls outside the technical system are followed

These require combined people, process and technology controls.

## Production Security Requirements

Before production deployment, additional controls would include:

- enterprise SSO
- strong API authentication
- workload/service identities
- TLS between services
- centralized secrets management
- network segmentation
- database encryption and restricted roles
- tamper-evident audit storage
- enterprise API gateway controls
- distributed rate limiting
- high availability
- backup and disaster recovery
- SIEM integration
- additional LCNC connectors
- software signing / provenance
- operational model monitoring

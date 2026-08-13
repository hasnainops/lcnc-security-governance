### Boundary 10 — Software Supply Chain

GitHub and CI contain:

- source code
- OPA policies
- Dockerfiles
- ML training code
- tests
- security workflows

Security validation includes:

- Python regression tests
- OPA policy tests
- SonarQube static analysis and Quality Gate
- Trivy vulnerability, secret, and misconfiguration scanning
- OWASP ZAP baseline DAST workflow
- Dependabot dependency and container update monitoring
- Docker Compose validation

Changes are validated with automated security checks.

---

## Threat Scenarios

| ID | Threat | Potential Impact | Current Mitigation | Residual Risk | Status |
|---|---|---|---|---|---|
| TM-01 | Unauthorized access to portal/API | Unauthorized governance operations | Localhost binding; OPA access-control capability | No enterprise SSO or strong API identity | Partial |
| TM-02 | Discovery or runtime credential compromise | Unauthorized LCNC inventory or control-plane access | `.env` excluded from Git; CI secret scanning; Vault AppRole for Governance API database access; dynamic PostgreSQL credentials | Local MVP still contains some environment-based demo secrets; production Vault hardening is required | Partial |
| TM-03 | Forged or incorrect source metadata | Incorrect governance decisions | Authenticated Appsmith discovery; persisted enterprise discovery evidence; unknown values remain unknown | A compromised or untrusted source platform can still provide false metadata | Partial |
| TM-04 | Governance workflow bypass | Risky application receives improper approval | Risk evaluation; OPA governance policy; persistent approval requests/events; required roles; hard BLOCK protection | Enterprise user authentication and signed approval identity are not implemented | Implemented / Residual |
| TM-05 | OPA policy tampering | Mandatory guardrails weakened | Policy stored in Git; read-only runtime mount; OPA tests; CI validation | Repository write access remains privileged | Implemented / Residual |
| TM-06 | Risk-model manipulation | Artificially low risk score | Deterministic explainable scoring; tests; versioned evidence | Repository compromise could modify scoring logic | Implemented / Residual |
| TM-07 | ML model manipulation or misleading output | Incorrect anomaly or classification recommendation | AI is advisory; authoritative classification remains governed; model versions and assessments are persisted | Synthetic training does not establish production accuracy | Implemented / Residual |
| TM-08 | Stale approval after material change | Changed application remains trusted | Material changes invalidate or mark ML, scan, risk, and governance evidence stale | Protection depends on discovery visibility of the change | Implemented / Residual |
| TM-09 | Sensitive-data exfiltration | Confidential or restricted data leaves the approved boundary | DLP inspection; Integration Gateway enforcement; unapproved, insecure, and restricted transfers blocked | Applications that bypass the governed gateway remain an enterprise integration risk | Implemented / Residual |
| TM-10 | Shadow application evades discovery | Unmanaged application remains outside governance | Appsmith continuous discovery plus normalized enterprise discovery ingestion and persisted source evidence | Coverage remains limited to configured source adapters | Implemented / Residual |
| TM-11 | Embedded secret in citizen application | Credential disclosure | Security Scanner detects possible embedded-secret conditions; Trivy/CI secret scanning | Metadata and repository scanning cannot detect every secret exposure path | Partial |
| TM-12 | DLP unavailable | Sensitive transfer bypass | Integration Gateway fails closed when DLP is unavailable | Service outage can block legitimate transfer activity | Implemented |
| TM-13 | OPA unavailable | Mandatory authorization bypass | Governance and access decisions fail closed | Availability depends on OPA | Implemented |
| TM-14 | Vulnerable code, container, or dependency | Control-plane compromise | SonarQube static analysis; Trivy vulnerability/secret/misconfiguration scanning; Dependabot; ZAP baseline workflow | Continuous maintenance, patching, rebuild, and runtime validation remain required | Implemented / Continuous |
| TM-15 | Audit-history tampering | Loss of trustworthy evidence | Historical assessment, decision, approval, privilege, training, and discovery records are persisted separately in PostgreSQL | Database evidence is not cryptographically tamper-evident | Partial |
| TM-16 | Monitoring information disclosure | Operational or security information exposed | Prometheus and Grafana are bound locally in the MVP | Production requires authentication and network segmentation | Partial |
| TM-17 | Excessive temporary privilege | Privileged action exceeds business need | Accountable JIT approval; action-scoped grants; TTL; OPA enforcement; automatic expiry and revoke events | Enterprise identity proofing and PAM integration remain production requirements | Implemented / Residual |
| TM-18 | Approval workflow manipulation | Improper approval or escalation bypass | Persistent approval requests/events; required roles; SLA escalation; human decision audit; hard BLOCK protection | Enterprise identity and signed approval evidence are not implemented | Implemented / Residual |
| TM-19 | Vault or dynamic credential misuse | Unauthorized database access | Vault AppRole authentication; scoped Vault policy; short-lived PostgreSQL credentials | Local Vault development mode is not production hardened | Implemented / Residual |
| TM-20 | Required training bypass | Governance approval despite unresolved training requirements | Automated training assignments; due/status tracking; training events; approval training gate | Enterprise LMS identity and attestation are not integrated | Implemented / Residual |

---

## Primary Abuse Case

### Scenario

A citizen developer creates an application that handles confidential customer data and connects to an unapproved external service.

### Risk Path

1. The citizen developer creates the application in Appsmith or another connected discovery source.
2. Continuous or enterprise discovery detects the application.
3. Discovery evidence is normalized and persisted.
4. Inventory comparison identifies its registration and governance state.
5. ML anomaly analysis evaluates unusual application characteristics.
6. ML classification suggests data sensitivity when sufficient metadata exists.
7. The Security Scanner identifies deterministic security findings.
8. The Risk Engine calculates an explainable risk score and contributing factors.
9. OPA evaluates mandatory governance policy.
10. The Governance API creates the governance outcome.
11. Governance Automation routes the application to the required approval path.
12. High-risk or blocked cases are assigned to the appropriate Security/GRC role.
13. Overdue approval requests can be escalated according to the configured SLA.
14. Dynamic Compliance records passed, failed, and not-assessed controls.
15. Required training is automatically assigned from identified control deficiencies.
16. Incomplete required training can prevent approval progression.
17. Human decisions, escalation events, training evidence, and governance outcomes are persisted.
18. A mandatory OPA BLOCK cannot be silently converted into approval.

If the application attempts an outbound sensitive transfer:

1. The Governance API obtains the authoritative application classification.
2. The Integration Gateway invokes the DLP Engine.
3. DLP identifies sensitive-data indicators.
4. The gateway combines authoritative classification, detected sensitivity, destination trust, and transport security.
5. The gateway returns ALLOW or BLOCK.
6. Safe transfer evidence is persisted.
7. Raw sensitive transfer content is not stored in the audit record.
---

## AI Threat Considerations

### Model Leakage

Governance outcomes, known shadow labels, approval outcomes, and risk scores are excluded from anomaly-model input features.

This reduces direct decision leakage between authoritative governance outcomes and AI anomaly analysis.

### False Positives and False Negatives

ML results are not treated as mandatory authorization.

OPA, deterministic risk scoring, the Security Scanner, DLP, the Integration Gateway, and Governance Automation remain separate control mechanisms.

A misleading ML result therefore cannot independently approve an application or privileged action.

### Synthetic Training Data

Current ML validation uses synthetic datasets.

Reported model metrics demonstrate implementation behavior only.

They are not production-accuracy claims.

Production deployment would require representative enterprise datasets, model validation, drift monitoring, and defined retraining governance.

### AI Overreach

The architecture intentionally separates responsibilities:

- ML performs anomaly detection and classification assistance.
- Deterministic controls identify explicit security conditions.
- OPA enforces mandatory policy.
- Governance Automation manages workflow state.
- Human stakeholders remain accountable for consequential organizational decisions.

AI output does not become final authorization.

---

## Fail-Closed Behavior

### OPA Unavailable

Mandatory governance and access authorization is not fabricated.

Requests that require OPA authorization fail rather than silently receiving permission.

### DLP Unavailable

Protected outbound-transfer evaluation blocks rather than bypassing sensitive-data inspection.

This protects confidentiality at the cost of temporary availability for legitimate transfers.

### Risk Engine Unavailable

Governance evaluation does not invent a risk result.

The workflow cannot represent a missing risk assessment as a successful assessment.

### Security Scanner Incomplete or Unavailable

Missing scanner evidence is not represented as a clean security scan.

### Missing Telemetry

Unknown information remains unknown or pending.

Missing source metadata is not converted to a safe default.

### Governance Automation Unavailable

A governance decision must not be represented as having completed an approval workflow when approval routing or accountable decision evidence could not be created.

Mandatory OPA BLOCK outcomes remain authoritative.

### Vault Unavailable

The Governance API cannot obtain new dynamic PostgreSQL credentials from Vault.

The system must not fall back to an embedded long-lived production database password.

Existing cached short-lived credentials remain usable only within their valid lifetime.

### Training Evidence Unavailable

Missing required-training evidence must not be interpreted as training completion.

Approval readiness must be based on recorded completion state.

---

## Secure Credential Handling

Current MVP controls:

- `.env` is excluded from Git.
- `.env.example` contains placeholders only.
- CI performs repository secret scanning.
- Vault provides centralized runtime secret services for Governance API database access.
- Governance API authenticates to Vault through AppRole.
- Vault policy limits access to the required database credential path.
- Vault's PostgreSQL secrets engine issues short-lived dynamic database credentials.
- Dynamic database credentials are not committed to source control.
- Governance API database connections use the dynamically issued identity.

Current MVP limitations:

- the local Vault instance runs in development mode for demonstration
- production Vault persistent storage is not configured
- production Vault HA is not configured
- TLS is not configured for local Vault communication
- production unseal and recovery procedures are not implemented
- not every local demonstration secret has been migrated into Vault

These limitations are production-hardening requirements rather than hidden MVP capabilities.

---

## Residual Risk

The platform cannot independently guarantee that:

- every enterprise LCNC platform or SaaS source is connected
- every shadow application is observable through configured discovery adapters
- source-platform metadata is truthful
- every enterprise network path is forced through the Integration Gateway
- administrators cannot misuse privileged host or infrastructure access
- all security findings are detectable from available metadata
- synthetic ML performance represents production accuracy
- enterprise identity accurately proves every human decision maker
- local PostgreSQL audit records are cryptographically tamper-evident
- all organizational controls outside the technical system are followed
- a local single-node deployment provides production availability or disaster recovery

These risks require combined people, process, identity, infrastructure, and technology controls.

---

## Production Security Requirements

Before production deployment, additional controls would include:

- enterprise SSO
- MFA
- strong API authentication
- workload and service identities
- TLS or mTLS between services
- production-hardened Vault
- persistent Vault storage
- Vault HA
- controlled unseal and recovery procedures
- broader migration of runtime secrets into managed secret paths
- network segmentation
- database encryption and restricted roles
- tamper-evident audit storage
- enterprise API gateway controls
- distributed rate limiting
- high availability
- backup and disaster recovery
- SIEM integration
- additional LCNC and enterprise security connectors
- enterprise PAM integration where appropriate
- enterprise LMS integration where appropriate
- software signing and provenance
- production ML validation
- model drift monitoring
- operational security monitoring
- tested incident-response and recovery procedures

The local MVP demonstrates the logical security-governance control architecture but does not claim these production capabilities.

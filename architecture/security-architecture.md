# LCNC Security Governance — MVP V5 Security Architecture

## Purpose

This artifact shows where security controls are placed across the MVP and which component owns each security decision.

The architecture intentionally separates:

- discovery
- AI-assisted analysis
- deterministic risk evaluation
- mandatory policy enforcement
- approval automation
- time-limited privileged access
- sensitive-data inspection
- secrets management
- audit evidence
- human accountability
- software security validation

## Security Control Architecture

```mermaid

flowchart TB

    DEV["Citizen Developer"]

    APPPROXY["Appsmith Edge Proxy<br/>Caddy"]
    APP["Appsmith<br/>restricted internal network"]

    SOURCES["Enterprise Discovery Sources"]
    DISC["Appsmith Discovery"]
    EDISC["Enterprise Discovery"]

    ML["ML Analytics"]
    RISK["Risk Engine"]
    SCAN["Security Scanner"]

    APIEDGE["Stable Governance API Endpoint<br/>Caddy"]
    APIA["Governance API A"]
    APIB["Governance API B"]
    AUTO["Governance Automation"]

    OPA["OPA"]
    JIT["JIT Privilege Lifecycle"]

    DLP["DLP Engine"]
    GW["Integration Gateway"]

    COMP["Dynamic Compliance"]
    GUIDE["Citizen Guidance"]
    TRAIN["Training Automation"]

    VAULT["Vault<br/>AppRole + Dynamic DB Credentials"]
    DB[("PostgreSQL Evidence Store")]

    PORTAL["Governance Portal"]

    PROM["Prometheus"]
    GRAF["Grafana"]

    TEST["pytest"]
    OPATEST["OPA Tests"]
    SONAR["SonarQube"]
    TRIVY["Trivy"]
    ZAP["OWASP ZAP Baseline"]
    DEPS["Dependabot"]

    DEV --> APPPROXY
    APPPROXY --> APP

    APP --> DISC
    APP --> APIEDGE

    SOURCES --> EDISC

    DISC --> APIEDGE
    EDISC --> ML
    EDISC --> APIEDGE

    APIEDGE --> APIA
    APIEDGE --> APIB

    APIA --> ML
    APIB --> ML

    APIA --> RISK
    APIB --> RISK

    APIA --> SCAN
    APIB --> SCAN

    APIA --> OPA
    APIB --> OPA

    APIA --> AUTO
    APIB --> AUTO

    APIA --> GW
    APIB --> GW

    APIA --> COMP
    APIB --> COMP

    APIA --> GUIDE
    APIB --> GUIDE

    AUTO --> JIT
    AUTO --> TRAIN
    JIT --> OPA

    GW --> DLP
    DLP --> GW

    APIA --> VAULT
    APIB --> VAULT

    VAULT --> DB

    APIA --> DB
    APIB --> DB
    AUTO --> DB

    PORTAL --> APIEDGE

    PROM --> APIEDGE
    PROM --> GW
    PROM --> OPA
    PROM --> GRAF

    TEST --> APIEDGE
    OPATEST --> OPA
    SONAR --> APIEDGE
    TRIVY --> APIEDGE
    ZAP --> APIEDGE
    DEPS --> TEST

```

## Decision Ownership

| Control | Primary Owner |
|---|---|
| Shadow IT / enterprise discovery | Discovery services |
| AI anomaly detection | ML Analytics |
| AI classification suggestion | ML Analytics |
| Deterministic application risk | Risk Engine |
| Deterministic security findings | Security Scanner |
| Mandatory governance policy | OPA |
| Fine-grained authorization | OPA |
| Approval routing and escalation | Governance Automation |
| Human approval accountability | Business / Security / GRC stakeholder |
| Temporary privileged access | Governance Automation + OPA |
| Sensitive-data detection | DLP Engine |
| Outbound-transfer enforcement | Integration Gateway |
| Dynamic compliance | Governance API |
| Training requirement automation | Governance API / Governance Automation |
| Dynamic database credentials | Vault |
| Durable evidence | PostgreSQL |
| Static code/security analysis | SonarQube |
| Vulnerability/secret/misconfiguration scanning | Trivy |
| Baseline runtime DAST | OWASP ZAP workflow |
| Dependency lifecycle | Dependabot |

## Trust and Enforcement Principles

AI evidence is advisory.

OPA remains the mandatory policy authority.

Human reviewers remain accountable for organizational decisions but cannot override a hard mandatory BLOCK through the approval automation path.

JIT grants are scoped and time-limited and remain subject to OPA guardrails.

DLP and the Integration Gateway fail closed for protected outbound-transfer evaluation.

Vault reduces long-lived database-secret exposure by issuing dynamic credentials to the Governance API.

Internal services remain on Docker service networks unless direct host/operator access is required.

Appsmith itself remains isolated on the internal `appsmith_restricted` network; localhost access is mediated by the dual-homed Caddy `appsmith-proxy`.

The stable Governance API endpoint uses Caddy health-aware load balancing across two stateless Governance API replicas. This demonstrates local API control-plane failover, not full-stack or stateful-service high availability.

## MVP Boundary

The local MVP demonstrates the control architecture.

Production deployment would add:

- enterprise identity and MFA
- workload identities
- TLS/mTLS
- production-hardened Vault
- network segmentation
- broader control-plane and stateful-service high availability beyond the demonstrated Governance API A/B failover
- backup and disaster recovery
- SIEM integration
- tamper-evident audit storage
- production source connectors
- production model monitoring

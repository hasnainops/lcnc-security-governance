# LCNC Security Governance Platform

**AI-assisted security and governance control plane for enterprise low-code/no-code environments.**

The platform helps organizations discover citizen-developed applications, assess security and data risk, enforce policy, and route applications through proportionate governance without unnecessarily slowing legitimate business innovation.

---

## Why This Platform Exists

> **You cannot secure what you cannot see.**

Low-code/no-code platforms allow business teams to build applications and automate processes faster, reducing dependence on traditional development backlogs.

At enterprise scale, that same accessibility can create governance challenges:

- Applications may exist outside normal IT visibility.
- Ownership and accountability may be unclear.
- Sensitive data may flow through unapproved integrations.
- Authentication, access control, and security configuration may be inconsistent.
- Security teams cannot manually review every citizen-developed application.

The problem is therefore not citizen development itself. The challenge is enabling it at scale while maintaining **visibility, security, accountability, and evidence**.

This platform addresses that gap by placing an external governance and security layer around low-code/no-code environments.

---

## What the Platform Does

The platform follows a continuous governance lifecycle:

```text
Discover
   ↓
Inventory
   ↓
Assess
   ↓
Control
   ↓
Decide
   ↓
Evidence
```

### Core Capabilities

- **Shadow IT discovery and application inventory**
  Identifies known and potentially unmanaged LCNC applications and maintains governance-relevant application metadata.

- **AI-assisted risk analysis**
  Uses machine-learning signals to identify anomalous application behavior and help prioritize investigation.

- **Deterministic risk assessment**
  Evaluates application characteristics such as ownership, data sensitivity, external integrations, credentials, and exposure using explainable control logic.

- **Security and compliance validation**
  Applies security scanning, policy checks, and data-protection controls before governance decisions are made.

- **Policy-as-code enforcement**
  Uses Open Policy Agent (OPA) and Rego policies to enforce mandatory security requirements independently of AI recommendations.

- **Data protection and controlled egress**
  Detects sensitive-data conditions and evaluates whether external destinations and integrations are permitted.

- **Risk-based governance workflows**
  Routes applications to automatic approval, human review, or blocking according to security and business risk.

- **Operational monitoring and evidence**
  Provides platform-health, governance, and functional evidence through the Unified Security & Governance View and supporting monitoring services.

---

> **Design principle:** AI identifies, assists, prioritizes, explains, and recommends. Deterministic controls assess. OPA enforces. Governance defines accountability. Humans retain final authorization.

## How the Platform Works

The platform separates **intelligence, control enforcement, governance, and human authorization** rather than allowing any single component to make unrestricted decisions.

```text
Enterprise / LCNC Telemetry
            ↓
        Discovery
            ↓
    Feature Extraction
            ↓
   ML-Assisted Analysis
            ↓
    Enriched Inventory
            ↓
 Security Scanner + DLP
            ↓
  Deterministic Risk Engine
            ↓
      OPA / Rego Policy
            ↓
    Governance Workflow
            ↓
 Approve / Review / Block
            ↓
 Monitoring + Audit Evidence
```

### Architecture Principles

**External governance layer**
Security and governance controls operate outside the LCNC platform itself, reducing dependence on any single low-code/no-code vendor.

**Separating intelligence from authority**
Machine learning helps identify anomalies and prioritize risk, but it does not independently authorize applications or override mandatory controls.

**Deterministic control assessment**
Risk rules evaluate known security and governance conditions using explainable, repeatable logic.

**Policy-as-code enforcement**
OPA and Rego provide an independent policy decision layer for mandatory security requirements.

**Human accountability**
Applications requiring judgment or risk acceptance are routed to governance reviewers rather than being automatically approved by AI.

**Evidence by design**
Decisions, health information, security findings, and governance outcomes are retained as operational and audit evidence.

### Architecture Documentation

Detailed design documentation is maintained in the repository:

- [System Architecture](architecture/system-architecture.md)
- [Security Architecture](architecture/security-architecture.md)
- [Network Architecture](architecture/network-architecture.md)
- [Data Flow Diagram](architecture/data-flow-diagram.md)
- [Governance Workflow](architecture/governance-workflow.md)
- [Enterprise Deployment Model](architecture/enterprise-deployment.md)
- [Threat Model](architecture/threat-model.md)
- [Unified Security & Governance View](architecture/unified-security-governance-view-design.md)

---
## Governance Decision Model

The platform applies proportionate governance rather than treating every citizen-developed application as equally risky.

Applications move through one of three governance outcomes:

| Outcome | Purpose |
|---|---|
| **Approve** | Low-risk applications that satisfy required security and governance controls can proceed without unnecessary manual delay. |
| **Review** | Applications with elevated or ambiguous risk are routed to a human governance reviewer for investigation, remediation, or risk acceptance. |
| **Block** | Applications or actions that violate mandatory security, data-protection, or policy requirements are prevented from proceeding. |

### Separation of Responsibilities

The decision process deliberately separates different forms of authority:

```text
ML / AI
Identify anomalies
Prioritize investigation
Explain signals
Recommend attention
        ↓
Deterministic Risk Controls
Assess known risk conditions
        ↓
OPA / Rego
Evaluate mandatory policy
        ↓
Governance Workflow
Route the decision
        ↓
Human Reviewer
Authorize, remediate, or accept risk where judgment is required
```

This prevents probabilistic AI output from becoming an unrestricted security decision-maker.

### Example Governance Outcomes

The implemented MVP demonstrates different governance paths, including:

- **Low-risk business workflow** — eligible for automatic approval when required controls are satisfied.
- **Unknown or higher-risk application** — routed for security and governance review.
- **Sensitive-data export scenario** — blocked when data-protection and egress controls are violated.

The intent is not to govern creativity. It is to govern the **risk created around it**.

---

## Enterprise Capabilities & Security Controls

The platform combines discovery, security engineering, governance automation, and operational assurance into a single control plane.

| Capability | Implementation Focus |
|---|---|
| **Shadow IT Discovery** | Identifies LCNC applications and governance-relevant metadata to improve enterprise visibility. |
| **Application Inventory** | Maintains ownership, integration, exposure, data-sensitivity, and risk context for discovered applications. |
| **AI-Assisted Analysis** | Uses machine-learning signals, including anomaly detection, to help prioritize applications requiring attention. |
| **Deterministic Risk Assessment** | Applies explainable risk logic independently of probabilistic AI recommendations. |
| **Security Scanning** | Evaluates application and dependency security findings as part of the governance process. |
| **Data Loss Prevention** | Evaluates sensitive-data conditions and supports enforcement of controlled application egress. |
| **Policy as Code** | Uses OPA and Rego to evaluate mandatory governance and security requirements. |
| **Governance Automation** | Routes applications through approval, review, remediation, or blocking workflows. |
| **Secrets Management** | Uses HashiCorp Vault for centralized secret handling and dynamic credential workflows. |
| **DevSecOps Controls** | Integrates automated testing, dependency management, security scanning, and quality validation into the development lifecycle. |
| **Observability** | Uses Prometheus and Grafana alongside service-health and functional-status checks. |
| **Audit Evidence** | Maintains governance decisions, control evidence, validation records, and change-management documentation. |

### Security Control Layers

The platform follows a layered model rather than relying on a single security mechanism:

```text
Visibility
   ↓
Discovery + Inventory
   ↓
Security Assessment
   ↓
Risk Evaluation
   ↓
DLP + Access + Egress Controls
   ↓
OPA Policy Enforcement
   ↓
Governance Decision
   ↓
Monitoring + Evidence
```

Security controls are designed to remain external to the LCNC application builder where practical, allowing governance to be applied consistently across different platforms and citizen-development use cases.

---

## Operational Evidence & Quality

The project includes implementation evidence, automated validation, operational monitoring, and audit records to demonstrate that the control plane is functioning as designed.

### Validated Project Evidence

Current validated evidence includes:

- **Final audit:** 18/18 project objectives assessed as `FULL`.
- **Automated tests:** 93/93 tests passing in the validated test baseline.
- **Sonar quality gate:** Passed.
- **Code coverage:** 80.2%.
- **Code duplication:** 0.57%.
- **New issues:** 0.
- **Security hotspots:** 0.
- **Service and functional health checks:** implemented across the platform.
- **Governance evidence:** application decisions and control outcomes retained for review.
- **Change management:** material platform changes documented through controlled change records.

### Operational Assurance

The platform uses multiple layers of operational assurance:

- **Prometheus** for metrics collection.
- **Grafana** for operational visualization.
- **Unified Security & Governance View** for consolidated platform and functional status.
- **HashiCorp Vault** for secrets-management workflows.
- **Automated health checks** for critical services.
- **Functional validation** to distinguish service availability from actual control functionality.
- **CI/CD validation** for testing, dependency management, security checks, and code-quality controls.

### Evidence & Audit Documentation

Supporting evidence is maintained in the repository:

- [Final Audit Report](compliance/final-audit-report-v5.md)
- [Evidence Catalog](compliance/evidence-catalog.md)
- [Requirement Validation Matrix](compliance/requirement-validation-matrix.md)
- [Control Matrix](compliance/control-matrix.json)
- [Change Management Records](governance/change-management/)

---

## Repository Structure & Major Components

The repository is organized by platform capability rather than by presentation or academic deliverable.

| Path | Purpose |
|---|---|
| `discovery/` | LCNC application discovery and inventory collection. |
| `enterprise-discovery/` | Enterprise-facing discovery and integration workflows. |
| `ml-analytics/` | Machine-learning analysis and anomaly-detection services. |
| `risk-engine/` | Deterministic application risk assessment. |
| `security-scanner/` | Security validation and scanning workflows. |
| `dlp-engine/` | Sensitive-data and data-loss-prevention controls. |
| `integration-gateway/` | Controlled integration and application egress handling. |
| `governance-api/` | Central governance API and platform status endpoints. |
| `governance-automation/` | Governance routing and workflow automation. |
| `governance-portal/` | Unified Security & Governance View. |
| `policies/` | OPA/Rego policy-as-code controls. |
| `vault/` | Secrets-management configuration and workflows. |
| `monitoring/` | Prometheus, Grafana, and observability configuration. |
| `database/` | Persistent data-layer configuration and initialization. |
| `architecture/` | System, security, network, data-flow, threat-model, and enterprise deployment documentation. |
| `governance/` | Governance standards, procedures, access-control requirements, and change-management records. |
| `compliance/` | Control mappings, validation evidence, and final audit documentation. |
| `tests/` | Automated platform and integration validation. |
| `.github/` | CI/CD, dependency-management, and repository automation configuration. |

The current MVP is composed of independently testable services coordinated through Docker Compose and supported by centralized governance, policy enforcement, secrets management, and observability.

---

## Deployment & Runtime Model

The current implementation is a containerized MVP coordinated through Docker Compose.

The runtime separates platform capabilities into independent services, including:

- governance API and portal;
- discovery and enterprise discovery;
- machine-learning analytics;
- deterministic risk assessment;
- security scanning;
- DLP controls;
- integration gateway;
- governance automation;
- OPA policy enforcement;
- Vault secrets management;
- PostgreSQL persistence;
- Prometheus and Grafana observability.

### Local MVP Runtime

The Docker Compose environment provides a reproducible way to run and validate the integrated platform locally.

Key exposed services include:

| Service | Port |
|---|---:|
| Governance Portal | `3000` |
| Grafana | `3001` |
| Governance API | `8000` |
| Risk Engine | `8001` |
| ML Analytics | `8002` |
| Security Scanner | `8003` |
| DLP Engine | `8004` |
| Integration Gateway | `8005` |
| Discovery | `8006` |
| Governance Automation | `8007` |
| Appsmith Reference Frontend | `8080` |
| OPA | `8181` |
| Vault | `8200` |
| SonarQube | `9000` |
| Prometheus | `9090` |
| PostgreSQL | `5432` |

### Enterprise Deployment Direction

The repository also documents an enterprise deployment model that extends the MVP architecture toward:

- stronger service isolation;
- centralized identity and access control;
- resilient secrets management;
- scalable observability;
- controlled network boundaries;
- production-grade policy enforcement;
- high-availability service deployment;
- enterprise audit and evidence retention.

The documented enterprise architecture is a design direction rather than a claim that the current Docker Compose environment is production-ready.

See [Enterprise Deployment Model](architecture/enterprise-deployment.md) for the detailed design.

---

## Current Scope & Limitations

This repository represents a functional enterprise security and governance MVP. Its current boundaries are intentionally documented so that demonstrated capabilities are not confused with future production requirements.

- **Docker Compose MVP**
  The current runtime is designed for integrated local validation and demonstration. It is not a production high-availability deployment.

- **Application-level controlled egress**
  The platform can apply DLP and destination controls to governed application flows, but it does not enforce all enterprise network egress.

- **Telemetry-based discovery**
  Discovery operates from LCNC and enterprise application telemetry and metadata. The MVP does not deploy an endpoint agent across employee devices.

- **No endpoint download monitoring**
  The platform does not claim to detect every file downloaded directly to an employee workstation.

- **External governance architecture**
  Appsmith is used as a reference LCNC frontend and integration point. Security assessment, risk logic, policy enforcement, and governance remain external to the LCNC platform.

- **Cloud architecture versus cloud implementation**
  Enterprise and cloud deployment patterns are documented, but the repository does not contain a complete production-ready infrastructure-as-code package.

- **Local service redundancy is not production HA**
  Multiple local service instances used for resilience testing should not be interpreted as a complete production high-availability architecture.

- **Human governance remains required**
  AI and automation reduce repetitive assessment work, but elevated risk, exceptions, and risk acceptance remain subject to accountable human review.

These boundaries preserve the core architectural principle of the project:

> **Automate where controls are deterministic. Assist where intelligence adds value. Escalate where human accountability is required.**

---

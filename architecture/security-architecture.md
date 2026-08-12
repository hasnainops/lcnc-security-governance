# LCNC Security Governance — Security Architecture

## Purpose

This artifact shows where security controls are placed across the MVP and which component owns each security decision.

The design intentionally separates:

- AI-assisted analysis
- deterministic risk evaluation
- mandatory policy enforcement
- sensitive-data inspection
- audit evidence
- human accountability

## Security Control Architecture

```mermaid
flowchart TB

    DEV["Citizen Developer"]
    APP["Appsmith"]

    DISC["Continuous Discovery"]

    ML["ML Analytics"]
    RISK["Risk Engine"]
    SCAN["Security Scanner"]

    API["Governance API"]

    OPA["OPA"]
    DLP["DLP Engine"]
    GW["Integration Gateway"]

    COMP["Dynamic Compliance"]
    GUIDE["Citizen Guidance / Training"]

    DB[("PostgreSQL Evidence Store")]

    PORTAL["Governance Portal"]

    CI["GitHub Actions"]
    TRIVY["Trivy"]
    DEPS["Dependabot"]

    DEV --> APP
    APP --> DISC

    DISC --> ML
    DISC --> API

    ML -->|"Advisory evidence"| API

    API --> RISK
    API --> SCAN
    API --> OPA
    API --> GW

    GW --> DLP

    API --> COMP
    COMP --> GUIDE

    API --> DB
    DB --> API

    API --> PORTAL

    CI --> TRIVY
    DEPS --> CI

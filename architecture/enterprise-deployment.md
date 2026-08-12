# LCNC Security Governance — Enterprise / Hybrid Deployment View

## Purpose

This artifact maps the localhost MVP to a realistic enterprise deployment model.

It separates:

- what exists in the current MVP
- how the same logical components would be deployed in an enterprise
- what additional production controls would be required

This is an architectural target, not a claim that the current MVP already includes all production capabilities.

## Hybrid Deployment Model

```mermaid
flowchart LR

    subgraph USERS["Enterprise Users"]
        DEV["Citizen Developers"]
        SEC["Security / GRC"]
        ADMIN["Platform Administrators"]
    end

    subgraph LCNC["LCNC Platforms"]
        APPSMITH["Appsmith"]
        OTHER["Other LCNC Platforms"]
    end

    subgraph EDGE["Enterprise Access Layer"]
        SSO["Enterprise SSO"]
        APIGW["API Gateway / WAF"]
    end

    subgraph CONTROL["Governance Control Plane"]
        PORTAL["Governance Portal"]
        API["Governance API"]
        DISC["Discovery Connectors"]

        ML["ML Analytics"]
        RISK["Risk Engine"]
        SCAN["Security Scanner"]
        OPA["OPA"]
        GW["Integration Gateway"]
        DLP["DLP Engine"]
        COMP["Dynamic Compliance"]
    end

    subgraph DATA["Protected Data Layer"]
        DB["PostgreSQL / Managed Database"]
        SECRETS["Enterprise Secrets Manager"]
        AUDIT["Immutable / Tamper-Evident Audit Store"]
    end

    subgraph OBS["Security & Operations"]
        PROM["Metrics Platform"]
        SIEM["SIEM / Security Analytics"]
        ALERT["Alerting / Incident Workflow"]
    end

    subgraph CICD["Software Supply Chain"]
        GIT["Git Repository"]
        CI["CI/CD Security Pipeline"]
        REG["Trusted Container Registry"]
    end

    DEV --> SSO
    SEC --> SSO
    ADMIN --> SSO

    SSO --> PORTAL
    SSO --> APIGW

    PORTAL --> APIGW
    APIGW --> API

    APPSMITH --> DISC
    OTHER --> DISC
    DISC --> API
    DISC --> ML

    API --> ML
    API --> RISK
    API --> SCAN
    API --> OPA
    API --> GW
    GW --> DLP
    API --> COMP

    API --> DB
    API --> AUDIT

    CONTROL --> SECRETS

    API --> PROM
    GW --> PROM
    PROM --> SIEM
    AUDIT --> SIEM
    SIEM --> ALERT

    GIT --> CI
    CI --> REG
    REG --> CONTROL

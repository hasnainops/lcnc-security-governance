# LCNC Security Governance — Network Architecture

## Purpose

This diagram shows which services are exposed to the Mac host and which remain internal to the Docker Compose network.

The MVP intentionally exposes only services required for the demo and administration.

```mermaid
flowchart TB

    USER["Browser / Operator"]

    subgraph HOST["Mac Host — localhost"]
        APPHOST["Appsmith<br/>127.0.0.1:8080"]
        APIHOST["Governance API<br/>127.0.0.1:8000"]
        PORTALHOST["Governance Portal<br/>127.0.0.1:3000"]
        GRAFHOST["Grafana<br/>127.0.0.1:3001"]
        PROMHOST["Prometheus<br/>127.0.0.1:9090"]
        OPAHOST["OPA<br/>127.0.0.1:8181"]
    end

    subgraph DOCKER["Docker Compose Network"]
        APP["Appsmith"]
        PORTAL["Governance Portal / Nginx"]
        API["Governance API"]

        DISC["Discovery"]
        RISK["Risk Engine :8001"]
        ML["ML Analytics :8002"]
        SCAN["Security Scanner :8003"]
        DLP["DLP Engine :8004"]
        GW["Integration Gateway :8005"]
        DB["PostgreSQL :5432"]

        OPA["OPA"]
        PROM["Prometheus"]
        GRAF["Grafana"]
    end

    USER --> APPHOST
    USER --> PORTALHOST
    USER --> APIHOST
    USER --> GRAFHOST
    USER --> PROMHOST
    USER --> OPAHOST

    APPHOST --> APP
    PORTALHOST --> PORTAL
    APIHOST --> API
    GRAFHOST --> GRAF
    PROMHOST --> PROM
    OPAHOST --> OPA

    PORTAL -->|"/api reverse proxy"| API

    DISC --> APP
    DISC --> API
    DISC --> ML

    API --> RISK
    API --> SCAN
    API --> OPA
    API --> GW
    API --> DB

    GW --> DLP

    API --> PROM
    GW --> PROM
    PROM --> GRAF

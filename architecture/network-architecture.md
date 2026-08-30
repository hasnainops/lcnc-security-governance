# LCNC Security Governance — Network Architecture

## Purpose

This diagram shows which services are exposed to the Mac host and which remain internal to the Docker Compose network.

The MVP intentionally exposes only services required for the demo and administration.

Appsmith itself remains only on the internal `appsmith_restricted` network. Localhost access on `127.0.0.1:8080` is provided by the dual-homed `appsmith-proxy`, which joins `appsmith_restricted` and `appsmith_edge`.

The stable Governance API endpoint on `127.0.0.1:8000` is a Caddy reverse proxy/load balancer. It joins `appsmith_restricted` and the default service network and routes traffic to two stateless Governance API replicas on the default network.

```mermaid

flowchart TB

    USER["Browser / Operator"]

    subgraph HOST["Mac Host — localhost"]
        APPHOST["Appsmith Access<br/>127.0.0.1:8080"]
        APIHOST["Governance API<br/>127.0.0.1:8000"]
        PORTALHOST["Governance Portal<br/>127.0.0.1:3000"]
        GRAFHOST["Grafana<br/>127.0.0.1:3001"]
        PROMHOST["Prometheus<br/>127.0.0.1:9090"]
        OPAHOST["OPA<br/>127.0.0.1:8181"]
    end

    subgraph EDGE["Published Edge"]
        APPPROXY["Appsmith Proxy<br/>Caddy<br/>restricted + edge"]
        APIEDGE["Governance API Endpoint<br/>Caddy<br/>restricted + default"]
    end

    subgraph RESTRICTED["appsmith_restricted — internal=true"]
        APP["Appsmith<br/>restricted network only"]
    end

    subgraph DEFAULT["Default Docker Service Network"]
        DISC["Appsmith Discovery<br/>restricted + default"]
        EDISC["Enterprise Discovery"]

        APIA["Governance API A<br/>:8000"]
        APIB["Governance API B<br/>:8000"]

        RISK["Risk Engine :8001"]
        ML["ML Analytics :8002"]
        SCAN["Security Scanner :8003"]
        DLP["DLP Engine :8004"]
        GW["Integration Gateway :8005"]
        AUTO["Governance Automation :8007"]

        DB["PostgreSQL :5432"]
        VAULT["Vault :8200"]
        OPA["OPA :8181"]

        PORTAL["Governance Portal / Nginx"]
        PROM["Prometheus :9090"]
        GRAF["Grafana"]
    end

    USER --> APPHOST
    USER --> APIHOST
    USER --> PORTALHOST
    USER --> GRAFHOST
    USER --> PROMHOST
    USER --> OPAHOST

    APPHOST --> APPPROXY
    APPPROXY --> APP

    APIHOST --> APIEDGE
    APIEDGE --> APIA
    APIEDGE --> APIB

    PORTALHOST --> PORTAL
    PORTAL -->|"/api reverse proxy"| APIEDGE

    GRAFHOST --> GRAF
    PROMHOST --> PROM
    OPAHOST --> OPA

    DISC --> APP
    DISC --> APIEDGE
    DISC --> ML

    EDISC --> APIEDGE
    EDISC --> ML

    APP -->|"governed API access"| APIEDGE

    APIA --> RISK
    APIB --> RISK

    APIA --> ML
    APIB --> ML

    APIA --> SCAN
    APIB --> SCAN

    APIA --> OPA
    APIB --> OPA

    APIA --> GW
    APIB --> GW

    APIA --> AUTO
    APIB --> AUTO

    APIA --> VAULT
    APIB --> VAULT

    VAULT --> DB
    GW --> DLP

    PROM --> APIEDGE
    PROM --> GW
    PROM --> OPA

    GRAF --> PROM

```

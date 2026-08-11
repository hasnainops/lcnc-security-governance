# Security Trust Boundaries

```mermaid
flowchart LR
    subgraph TB1["Trust Boundary 1 — Citizen Development Platform"]
        APP["Appsmith Applications"]
    end

    subgraph TB2["Trust Boundary 2 — Discovery"]
        DISC["Authenticated Discovery Adapter"]
    end

    subgraph TB3["Trust Boundary 3 — Governance Control Plane"]
        API["Governance API"]
        RISK["Risk Engine"]
        OPA["OPA Policy Engine"]
        DB["PostgreSQL Evidence Store"]
    end

    subgraph TB4["Trust Boundary 4 — Governance Experience"]
        PORTAL["Governance Portal"]
    end

    subgraph TB5["Trust Boundary 5 — Observability"]
        PROM["Prometheus"]
        GRAFANA["Grafana"]
    end

    subgraph TB6["Trust Boundary 6 — Software Supply Chain"]
        GIT["GitHub Repository"]
        CI["Security Validation CI"]
        TRIVY["Trivy"]
    end

    APP -->|Application metadata| DISC
    DISC -->|Normalized inventory data| API

    API -->|Application facts| RISK
    RISK -->|Score + explainable factors| API

    API -->|Application facts| OPA
    OPA -->|ALLOW / DENY| API

    API -->|Persist evidence| DB
    PORTAL -->|Governance operations| API

    API -->|Metrics| PROM
    PROM --> GRAFANA

    GIT --> CI
    CI --> TRIVY
    CI -->|Validated changes| GIT
```

## Fail-Closed Behavior

### Risk Engine failure

Risk Engine unavailable → 503 Service Unavailable → no policy decision → no governance authorization.

### OPA failure

OPA unavailable → 503 Service Unavailable → no governance authorization.

## Security Principle

Mandatory governance dependencies fail closed. The system does not manufacture an approval when a required decision component is unavailable.

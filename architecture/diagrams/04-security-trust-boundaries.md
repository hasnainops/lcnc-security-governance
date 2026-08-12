# Security Trust Boundaries — MVP V2

```mermaid
flowchart LR

    subgraph TB1["1 — Citizen Development"]
        DEV["Citizen Developer"]
        APP["Appsmith"]
        DEV --> APP
    end

    subgraph TB2["2 — Continuous Discovery"]
        DISC["Discovery Adapter<br/>60-second cycle"]
    end

    subgraph TB3["3 — AI / ML Analytics"]
        ML["ML Analytics"]
        ANOM["Isolation Forest"]
        CLASS["TF-IDF + Logistic Regression"]
        ML --> ANOM
        ML --> CLASS
    end

    subgraph TB4["4 — Governance Control Plane"]
        API["Governance API"]
        RISK["Risk Engine"]
        SCAN["Security Scanner"]
        COMP["Dynamic Compliance"]
        GUIDE["Citizen Guidance / Training"]
    end

    subgraph TB5["5 — Mandatory Policy"]
        OPA["OPA"]
        GOV["Governance Policy"]
        ACCESS["Access Policy"]
        OPA --> GOV
        OPA --> ACCESS
    end

    subgraph TB6["6 — Sensitive Data / Egress"]
        GW["Integration Gateway"]
        DLP["DLP Engine"]
        GW --> DLP
    end

    subgraph TB7["7 — Evidence"]
        DB["PostgreSQL"]
    end

    subgraph TB8["8 — Governance Experience"]
        PORTAL["Governance Portal"]
        NGINX["Nginx /api Proxy"]
        PORTAL --> NGINX
    end

    subgraph TB9["9 — Observability"]
        PROM["Prometheus"]
        GRAF["Grafana"]
        PROM --> GRAF
    end

    subgraph TB10["10 — Software Supply Chain"]
        GIT["GitHub"]
        CI["GitHub Actions"]
        TRIVY["Trivy"]
        DEP["Dependabot"]
        GIT --> CI
        CI --> TRIVY
        DEP --> GIT
    end

    APP -->|"LCNC metadata"| DISC

    DISC -->|"inventory"| API
    DISC -->|"analysis"| ML
    ML -->|"advisory AI evidence"| API

    API --> RISK
    RISK -->|"score + factors"| API

    API --> SCAN
    SCAN -->|"findings"| API

    API --> OPA
    OPA -->|"ALLOW / DENY"| API

    API --> GW
    DLP -->|"sensitivity"| GW
    GW -->|"ALLOW / BLOCK"| API

    API --> COMP
    COMP --> GUIDE

    API --> DB
    DB --> API

    NGINX --> API

    API --> PROM
    GW --> PROM

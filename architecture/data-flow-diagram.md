# LCNC Security Governance — Data Flow Diagram

## Purpose

This artifact shows how application metadata, AI evidence, security findings, sensitive transfer data, governance decisions, and audit evidence move through the MVP.

## DFD — Level 1

```mermaid
flowchart LR

    DEV["Citizen Developer"]
    APP["Appsmith"]
    DISC["Continuous Discovery"]
    ML["ML Analytics"]
    API["Governance API"]
    RISK["Risk Engine"]
    SCAN["Security Scanner"]
    OPA["OPA"]
    GW["Integration Gateway"]
    DLP["DLP Engine"]
    DB[("PostgreSQL Evidence Store")]
    PORTAL["Governance Portal"]
    PROM["Prometheus / Grafana"]

    DEV -->|"Creates / modifies app"| APP

    APP -->|"Application metadata"| DISC

    DISC -->|"Inventory + observed telemetry"| API
    DISC -->|"ML feature metadata"| ML

    ML -->|"Anomaly assessment"| API
    ML -->|"Classification suggestion + confidence"| API

    API -->|"Normalized application facts"| RISK
    RISK -->|"Risk score + factors"| API

    API -->|"Application metadata"| SCAN
    SCAN -->|"Findings + severity"| API

    API -->|"Governance / access facts"| OPA
    OPA -->|"ALLOW / DENY + reasons"| API

    API -->|"Transfer request context + content"| GW
    GW -->|"Content + field names"| DLP
    DLP -->|"Sensitivity metadata only"| GW
    GW -->|"ALLOW / BLOCK + safe DLP evidence"| API

    API -->|"Current state + historical evidence"| DB
    DB -->|"Inventory + audit history"| API

    PORTAL -->|"Same-origin /api requests"| API
    API -->|"Dashboard evidence"| PORTAL

    API -->|"Operational metrics"| PROM
    GW -->|"Gateway metrics"| PROM

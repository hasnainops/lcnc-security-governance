# LCNC Security Governance — Governance and Security Workflow

## Purpose

This workflow shows how a citizen-developed application moves from discovery through AI-assisted analysis, deterministic security controls, governance decision, remediation, reassessment, and developer guidance.

## End-to-End Workflow

```mermaid
flowchart TD

    A["Citizen Developer creates or changes app"]
    B["Appsmith"]
    C["Continuous Discovery"]
    D{"Known application?"}

    E["Register as unregistered / shadow candidate"]
    F["Refresh inventory metadata"]

    G{"Required telemetry available?"}

    H["ML Anomaly Detection"]
    I["AI-Assisted Classification"]
    J["Security Scanner"]

    K["Mark missing analysis as pending"]

    L["Risk Engine"]
    M["OPA Governance Policy"]

    N{"OPA decision"}

    O["BLOCK"]
    P["Governance Workflow"]

    Q{"Workflow outcome"}

    R["AUTO_APPROVE"]
    S["BUSINESS_REVIEW"]
    T["SECURITY_REVIEW"]

    U["Persist Evidence"]

    V["Dynamic Compliance"]
    W["Security Score + Badge"]
    X["Targeted Guidance / Training"]

    Y["Remediation"]
    Z["Application metadata changes"]

    A --> B
    B --> C

    C --> D

    D -->|"No"| E
    D -->|"Yes"| F

    E --> G
    F --> G

    G -->|"Yes"| H
    G -->|"Yes"| I
    G -->|"Yes"| J

    G -->|"No"| K

    H --> L
    I --> L
    J --> L
    K --> L

    L --> M

    M --> N

    N -->|"DENY"| O
    N -->|"ALLOW"| P

    P --> Q

    Q --> R
    Q --> S
    Q --> T

    O --> U
    R --> U
    S --> U
    T --> U

    U --> V
    V --> W
    W --> X

    X --> Y
    Y --> Z
    Z --> C

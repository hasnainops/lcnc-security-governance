# Live Demo Sequence

```mermaid
sequenceDiagram
    actor Developer as Citizen Developer
    participant Appsmith
    participant Discovery
    participant API as Governance API
    participant Risk as Risk Engine
    participant OPA
    participant DB as PostgreSQL
    participant Portal as Governance Portal

    Developer->>Appsmith: Create Customer Data Export
    Discovery->>Appsmith: Enumerate applications
    Discovery->>API: Register unknown application
    API->>DB: Persist shadow application

    Note over API,DB: Initial state: unregistered / unknown owner / unknown classification

    API->>Risk: Assess enriched application facts
    Risk-->>API: 90 CRITICAL + explainable factors

    API->>OPA: Evaluate confidential + unapproved external integration
    OPA-->>API: DENY

    API->>DB: Persist risk + policy + BLOCK
    API-->>Portal: BLOCK / Security-GRC Reviewer

    Note over Portal: Remediation performed

    Portal->>API: Register owner and remove external integration
    API->>DB: Mark prior risk/governance state stale

    Portal->>API: Re-run governance evaluation
    API->>Risk: Reassess
    Risk-->>API: 20 LOW

    API->>OPA: Re-evaluate application facts
    OPA-->>API: ALLOW

    API->>DB: Persist new governance decision
    API-->>Portal: AUTO_APPROVE

    Note over DB,Portal: Previous BLOCK remains in audit history
```

## Demo Story

1. Discover an unmanaged LCNC application.
2. Enrich its security context.
3. Explain why risk becomes CRITICAL.
4. Show OPA independently enforcing DENY.
5. Show governance returning BLOCK and assigning Security/GRC review.
6. Remediate the application.
7. Reassess to LOW risk.
8. Show OPA ALLOW and AUTO_APPROVE.
9. Prove that the original BLOCK remains in the audit history.

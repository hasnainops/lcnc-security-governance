# Governance Evidence Catalog

| Evidence | Source | Purpose | Persistence |
|---|---|---|---|
| Application inventory | PostgreSQL `applications` | Asset visibility and ownership | Durable |
| Discovery timestamps | `first_discovered_at`, `last_seen_at` | Continuous discovery evidence | Durable |
| Risk assessments | `risk_assessments` | Risk scoring and explanation | Durable |
| Policy decisions | `policy_decisions` | OPA ALLOW/DENY evidence | Durable |
| Governance decisions | `governance_decisions` | Approval/block/review evidence | Durable |
| Risk factors | Risk assessment JSON | Explainability | Durable |
| Policy reasons | OPA decision JSON | Enforcement rationale | Durable |
| Required role | Governance decision | Accountability | Durable |
| Governance history API | Governance API | Evidence retrieval | Runtime + durable backend |
| Governance Portal | Browser UI | Human-readable evidence | Runtime |
| Prometheus metrics | Prometheus | Operational telemetry | Time-series |
| Grafana dashboard | Grafana | Operational visualization | Runtime + provisioned config |
| OPA tests | `policies/application_test.rego` | Policy validation | Git |
| Risk tests | `tests/test_risk_engine.py` | Scoring validation | Git |
| Trivy scan | GitHub Actions | Security validation | CI history |
| Git commit history | Git/GitHub | Change traceability | Git |

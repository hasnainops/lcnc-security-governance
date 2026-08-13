# Governance Evidence Catalog — MVP V3

| Evidence | Source | Purpose | Persistence |
|---|---|---|---|
| Application inventory | PostgreSQL `applications` | Asset visibility and ownership | Durable |
| Discovery timestamps | `first_discovered_at`, `last_seen_at` | Continuous discovery evidence | Durable |
| Enterprise discovery evidence | `enterprise_discoveries` | Multi-source discovery, source identity and ML handoff evidence | Durable |
| Risk assessments | `risk_assessments` | Explainable deterministic risk | Durable |
| ML anomaly assessments | ML assessment tables | AI anomaly evidence and model version | Durable |
| ML classification assessments | Classification assessment tables | AI-assisted classification evidence | Durable |
| Security scans/findings | Scanner persistence | Deterministic application-security evidence | Durable |
| Policy decisions | `policy_decisions` | OPA ALLOW/DENY evidence | Durable |
| Governance decisions | `governance_decisions` | Governance outcome evidence | Durable |
| Approval requests | `approval_requests` | Approval route, required role and SLA state | Durable |
| Approval events | `approval_events` | Routing, escalation and human-decision audit trail | Durable |
| Access decisions | `access_decisions` | Fine-grained OPA authorization evidence | Durable |
| JIT privilege requests | `privilege_requests` | Privilege request and justification | Durable |
| JIT privilege grants | `privilege_grants` | Time-limited privileged authorization | Durable |
| JIT privilege events | `privilege_events` | Approval, expiry and revoke audit trail | Durable |
| Transfer decisions | Integration transfer events | DLP/gateway ALLOW/BLOCK evidence | Durable |
| Compliance assessments | Compliance persistence | Historical control snapshots | Durable |
| Training completions | `training_completions` | Citizen-developer completion evidence | Durable |
| Training assignments | `training_assignments` | Required training, subject and due date | Durable |
| Training events | `training_events` | Training lifecycle audit history | Durable |
| Governance history API | Governance API | Evidence retrieval | Runtime + durable backend |
| Governance Portal | Browser UI | Human-readable governance evidence | Runtime |
| Governance Automation UI/API | `localhost:8007` | Approval, escalation and JIT visibility | Runtime |
| Prometheus metrics | Prometheus | Operational telemetry | Time-series |
| Grafana dashboard | Grafana | Operational visualization | Runtime + provisioned config |
| Vault AppRole | Vault | Workload authentication evidence | Runtime configuration |
| Vault dynamic PostgreSQL identity | Vault database secrets engine | Short-lived database credentials | Runtime |
| SonarQube analysis | SonarQube | Static security/code-quality evidence | SonarQube |
| ZAP baseline workflow | GitHub Actions workflow | Runtime DAST configuration | Git / CI when executed |
| Trivy scanning | GitHub Actions | Vulnerability, secret and misconfiguration validation | CI history |
| Dependabot configuration | `.github/dependabot.yml` | Dependency/container update lifecycle | Git |
| Python regression tests | `pytest` | Application/control validation | Git + test output |
| OPA policy tests | `policies/*_test.rego` | Governance/access policy validation | Git + test output |
| Git commit history | Git/GitHub | Change traceability | Git |

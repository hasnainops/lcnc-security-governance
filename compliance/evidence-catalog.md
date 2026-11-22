# Governance Evidence Catalog — MVP V5

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
| Vault workload AppRoles | Vault | Dedicated workload authentication and policy isolation | Runtime configuration |
| Vault dynamic PostgreSQL identities | Vault database secrets engine | 15-minute least-privilege database credentials | Runtime |
| Vault-managed Appsmith integration credential | Vault KV v2 | Scoped integration credential storage without workload environment exposure | Runtime configuration |
| Objective 14 secrets-management evidence | `compliance/evidence/objective14-secrets-management.md` | Dynamic credentials, least privilege, token renewal, SecretID revocation and recovery | Git + runtime proof |
| SonarQube analysis | SonarQube | Static security/code-quality evidence | SonarQube |
| ZAP baseline workflow | GitHub Actions workflow | Runtime DAST configuration | Git / CI when executed |
| Trivy scanning | GitHub Actions | Vulnerability, secret and misconfiguration validation | CI history |
| Dependabot configuration | `.github/dependabot.yml` | Dependency/container update lifecycle | Git |
| Objective 15 vulnerability remediation | `compliance/evidence/objective15-vulnerability-remediation.md` | Detect, patch, validate, approve, redeploy and re-scan evidence | Git + runtime proof |
| Python regression tests | `pytest` | Application/control validation | Git + test output |
| OPA policy tests | `policies/*_test.rego` | Governance/access policy validation | Git + test output |
| Git commit history | Git/GitHub | Change traceability | Git |

## LO4.3 — Final live acceptance (2026-11-22)

**Status: PASS (MVP laboratory scope).**

The final live Appsmith acceptance supersedes earlier pending
LO4.3 acceptance assessments.

- Permitted HTTPS delivery: verified, HTTP 200.
- Restricted transfers: two blocked before outbound execution.
- Independent receiver: exactly one permitted POST.
- Persisted enforcement receipts: verified.
- Tested network bypass boundary: documented.
- Temporary authorization: revoked and cleaned.
- Original destination allowlist: restored on both backends.

Detailed evidence: [LO4.3 live acceptance](lo4-3-egress-acceptance.md).

Production-wide enforcement is not claimed.

## LO5.1 — Automated DevSecOps security-gate acceptance

**Technical result:** PASS within the isolated CI/CD
acceptance boundary.

Primary evidence:
[LO5.1 CI gate and approved deployment acceptance](evidence/lo5-1-ci-gate-acceptance.md)

- Synthetic runtime .env rejection:
  GitHub Actions run 45021988737.
- Corrected CI revision passed:
  GitHub Actions run 45022288718.
- Vulnerable image blocked:
  GitHub Actions run 45022980372.
- Retained Trivy evidence identified
  HIGH CVE-2026-85091 in zlib1g:
  GitHub Actions run 45024747226.
- Patched image passed pre-deployment Trivy:
  GitHub Actions run 45025213924.
- Reviewer-gated deployment, runtime health,
  exact image identity and post-deployment rescan:
  GitHub Actions run 45025760057.

Validated and deployed image ID:

`sha256:2170134851a82c924212978374eb7610aae9aca1d05113f906f674d04d2d50ac`

The isolated workflow had zero blocking
HIGH/CRITICAL findings after remediation.

**Boundary:** This was an isolated CI-runner
deployment, not a production rollout.
Comprehensive DAST, required branch checks,
mandatory SonarCloud quality-gate enforcement
and retesting of the integrated assurance revision
are not established by this evidence.

## LO5.2 — Secrets Management and Secure Credential Handling

**Acceptance:** PASS for the documented local MVP,
based on existing Objective 14 runtime evidence
and the LO5.2 documentary traceability review.

Primary acceptance record:
[LO5.2 secrets-management acceptance](evidence/lo5-2-secrets-management-acceptance.md)

Original runtime evidence:
[Objective 14 secrets-management evidence](evidence/objective14-secrets-management.md)

Documented controls include:

- Dedicated Vault AppRoles and scoped policies
- Vault-generated, short-lived PostgreSQL credentials
- Database least-privilege and cross-role access denial
- Protected file-based AppRole SecretID delivery
- Scoped Vault KV v2 Appsmith integration credential
- Renewable Vault service tokens
- SecretID revocation and authentication denial
- Fresh SecretID issuance and service recovery

Historical Objective 14 regression evidence:

- Python: 48 tests passed
- OPA: 15/15 tests passed
- Docker Compose validation: PASS

LO5.2 Steps 110–112 verified documentation and
tracked implementation-file references. These
steps did not rerun live Vault acceptance tests.

**Limitations:** The Appsmith platform account
password remains static and Vault-managed,
not dynamically generated by Vault. Its
platform-level rotation was not demonstrated.

Production Vault TLS, persistent storage,
high availability and operational recovery
remain outside the demonstrated local MVP.

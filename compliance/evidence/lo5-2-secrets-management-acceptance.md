# LO5.2 — Secrets Management Acceptance

## Official requirement

Implement secrets management and secure credential
handling for integrations.

## Acceptance scope

This assessment covers the existing local MVP.

It reconciles Objective 14 implementation and
previously recorded runtime evidence with LO5.2.

No live Vault operations, credential changes,
or regression tests were performed during this
LO5.2 documentary review.

## Primary evidence

[Objective 14 — Secrets Management and Secure Credential Handling](objective14-secrets-management.md)

Existing requirement mapping:
`compliance/requirement-validation-matrix.md`,
Section 12 — Secure Credential Handling.

## Verified documentary coverage

| Control | Existing Objective 14 evidence | Assessment |
|---|---|---|
| Centralized secrets management | Vault runtime secrets service | DOCUMENTED |
| Workload authentication | Four dedicated AppRoles and scoped policies | DOCUMENTED |
| Database credentials | Vault-generated PostgreSQL credentials with 15-minute lifetime | DOCUMENTED |
| Least privilege | Database grant and cross-role access-denial tests | DOCUMENTED |
| SecretID delivery | Protected runtime files with mode 0600 | DOCUMENTED |
| Appsmith integration | Scoped Vault KV v2 credential access | DOCUMENTED |
| Service token lifecycle | Renewable token behavior tested previously | DOCUMENTED |
| Revocation | Active Appsmith Discovery SecretID destroyed and rejected | DOCUMENTED |
| Recovery | Fresh SecretID issued and authentication restored | DOCUMENTED |

## Workload identities

The existing implementation documents separate
Vault identities for:

- Governance API
- Enterprise Discovery
- Governance Automation
- Appsmith Discovery

Associated policies:

- `vault/governance-api.hcl`
- `vault/enterprise-discovery.hcl`
- `vault/governance-automation.hcl`
- `vault/appsmith-discovery.hcl`

Existing runtime evidence reports denied
cross-workload Vault access and database
least-privilege restrictions.

## Credential lifecycle

### Provisioning

Vault AppRole provides workload authentication.

Database workloads obtain dynamic credentials
from the Vault PostgreSQL secrets engine.

AppRole SecretIDs are delivered through
protected runtime files rather than ordinary
application environment variables.

### Renewal

Objective 14 records successful renewable
Vault service-token behavior.

This is not equivalent to proving rotation
of every platform password or credential.

### Revocation

The existing Appsmith Discovery acceptance
test destroyed an active SecretID and
verified that authentication using the
revoked credential was rejected.

### Recovery

The existing evidence records successful
authentication using a newly issued SecretID.

The revoked credential was not restored
or reused.

## Appsmith credential boundary

The Appsmith integration credential is
managed in Vault KV v2 under:

`secret/integrations/appsmith`

The Appsmith platform account password
remains a static, platform-issued password.

Vault does not dynamically generate that
Appsmith account password.

Platform-level Appsmith password rotation
was not exercised in the Objective 14 proof.

## Existing regression evidence

Objective 14 records:

- Python tests: 48 passed
- OPA tests: 15/15 passed
- Docker Compose validation: PASS
- Python syntax validation: PASS
- Vault bootstrap shell syntax: PASS

These are historical results recorded in
Objective 14, not new LO5.2 test executions.

## Implementation traceability

Tracked implementation and verification files
were checked during LO5.2 Step 111:

- `scripts/bootstrap-vault.sh`
- `vault/governance-api.hcl`
- `vault/enterprise-discovery.hcl`
- `vault/governance-automation.hcl`
- `vault/appsmith-discovery.hcl`
- `discovery/appsmith_discovery.py`
- `tests/test_governance_database_vault.py`
- `tests/test_vault_database_helpers.py`
- `tests/test_governance_automation_credentials.py`
- `tests/test_credential_rotation.py`
- `tests/test_credential_maintenance.py`
- `docs/runbooks/credential-maintenance.md`

File presence and evidence-marker checks
establish traceability, not an independent
runtime retest.

## Production limitations

The local MVP does not establish a
production-hardened Vault deployment.

The documented production extensions include:

- Vault transport TLS
- Persistent Vault storage
- Vault high availability
- Operational unseal and disaster recovery
- Production credential lifecycle operations

Appsmith platform-password rotation also
remains outside the demonstrated acceptance.

## LO5.2 assessment

Technical acceptance:
PASS based on existing Objective 14 evidence
within the documented local MVP boundary.

No new implementation gap was established by
the documentary traceability review.

Independent live-runtime revalidation was
not performed during Steps 110–111.

Governance documentation reconciliation:
COMPLETE within the documented local MVP scope.

Repository publication and synchronization are
verified separately through Git history.

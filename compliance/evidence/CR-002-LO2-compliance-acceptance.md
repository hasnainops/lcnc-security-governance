# CR-002 — LO2 Final Compliance Acceptance

## 1. Scope and disposition

- Date: 2026-11-21 UTC
- Repository: lcnc-security-governance
- Branch: audit/learning-objective-assurance
- Learning area: LO2 — Automated Security and Compliance Validation
- Disposition: Scoped functional acceptance and operational recovery complete.
- Remaining coverage limitations are explicitly retained.

This record supplements:

- CR-002-LO2-native-publication-acceptance.md
- CR-002-LO2-route-and-scanning-acceptance.md
- CR-002-LO2-Appsmith-publish-denial-checkpoint.md

The acceptance does not establish universal production enforcement.

## 2. LO2.1 — Policy-as-code enforcement

Verified native Appsmith publication of approved release A,
followed by denial of modified release B under the previous approval.

Positive native publication:

- Native application: 6affb740b82ed4d1f79df9fb
- HTTP response: 200
- Governance preflight: 204
- Release A SHA256:
  0b01d4ccd3393af8b57d098845b747e8d363b934a2719cc9bdb75bc408766a59
- Observation: bf5b0695-eb86-463f-b549-716026ed9edd
- Authorization receipt: cd1774cf-6b0b-4ae7-96ad-e45f692074d6

Negative native publication:

- Modified release B: HTTP 403
- Authorization receipt: 8ab2f643-dbbd-488e-89b8-8cb964ebf53b
- Previously published release A remained unchanged.
- Release B remained a draft.

Alternate route evidence:

- Governance proxy rejected unreviewed create and clone requests.
- Git publication delegates to the guarded publication path,
  supported by source inspection and targeted tests.
- Live Git publication acceptance was not performed.

Native Appsmith laboratory source:

- Branch: audit/lo2-native-publish
- Commit: c43614b584bb708c0873110d6383c2df3ab2af56
- This is a separate local laboratory repository.

## 3. LO2.2 — Automated security scanning

Discovery automatically scanned changed Appsmith workflow metadata.

A live insecure HTTP action was introduced without executing it.

- Finding: SEC-009
- Description: Workflow contains unencrypted HTTP actions
- Severity: high
- Observation: cf452ed2-0858-465a-bbba-b8aaaca64d50
- Security scan: 15e0037d-9eac-4a04-b30d-8ec0c8a4a0d2

The insecure action was subsequently removed.

- Observation: ac3174d2-2df5-4f41-8e42-10b31f19c608
- Security scan: 59e8947b-b121-485d-8fa4-dac08da937f8
- Scan result: passed
- Historical adverse findings retained.

Integration-dependent coverage remains limited when connector
identity or collection evidence is incomplete.

## 4. LO2.3 — Dynamic compliance validation

Seven evidence-based compliance controls are implemented.

### CTRL-06 — Operation-level enforcement evidence

Application: LO2 Publish Allow Fixture

- Governance application: b18135b7-fbed-42a7-9267-0b496e351891
- Native application: 6afd4df965d61d1e1b332ae1
- Actual governance proxy response: HTTP 403
- Response marker: LCNC-PUBLISH-DENIED
- Access decision: 65198ed8-53cc-4325-87fd-163d90d7220b
- Governance decision: 83de59e0-8de2-4b95-8771-af169b16f5c3
- Evaluated: 2026-11-21T07:10:11.030792+00:00
- Enforcement verified: 2026-11-21T07:10:11.146509+00:00
- CTRL-06 result: pass
- Compliance summary: 6 pass, 0 fail, 1 not assessed.

Migration 028 introduced verified proxy-denial evidence fields
and validation constraints.

A privileged laboratory verifier recorded the actual HTTP denial
against the matching persisted access decision.

This is independently observed operation-level acceptance evidence,
not automatic production enforcement telemetry. It does not prove
universal authorization enforcement.

### CTRL-07 — Current authenticated release review

Application: LO2 Isolated Publish Fixture

- Governance application: ee0752ad-17e1-466f-92bc-6bbe2108f173
- Native application: 6affb740b82ed4d1f79df9fb
- Fresh observation: bf2d3faa-e0b7-4ea7-aed4-b698472980f6
- Governance decision: 45d6b20a-c303-42eb-bb17-36f288d01cfc
- Approval request: 7862b9f4-eff1-49bd-a5a7-7d1e4d85a303
- Approval time: 2026-11-21T08:17:09.224945+00:00
- Manifest version: appsmith-release-manifest-v1
- Release B SHA256:
  129876d2d1b5b45140bdb5fbc55d926eb90c53a3606a9f49e16c2374198a99da

Verified prerequisites:

- Authoritative classification: internal
- Risk assessment: assessed, low
- External integrations: 0
- Unapproved integrations: 0
- Security scan: passed
- ML anomaly: false
- ML advisory classification: public
- ML advisory confidence: 0.3515
- Classification review required: true
- Mandatory training: completed
- Vault authentication: HTTP 200
- Reviewer policy: lcnc-security-reviewer
- Explicit human approval: recorded
- Approval endpoint: HTTP 200
- Observation age before approval: 5.5 seconds

Results:

- Before approval: CTRL-07 not_assessed
- After approval: CTRL-07 pass
- Before: 5 pass, 0 fail, 2 not assessed
- After: 6 pass, 0 fail, 1 not assessed
- Temporary reviewer token revoked.
- No native publication of release B requested.

The verified review is bound to the current governance decision
and release evidence. Expired or changed evidence must not be
treated as a permanently valid authorization.

The Appsmith authentication redirect workaround was applied
only in the controlled acceptance harness.

The isolated fixture was not continuously monitored by the
stock Appsmith Discovery worker.

CTRL-06 and CTRL-07 passed on separate fixtures.
No simultaneous seven-of-seven result is claimed.

## 5. Risk assessment connection lifecycle correction

A closed database connection caused HTTP 500 during risk
assessment following changed workflow evidence.

The implementation was corrected to preserve independent
and borrowed connection ownership.

Live reassessment:

- Assessment: 8145d949-ee42-43a4-8f70-982bfee5472f
- Time: 2026-11-21T07:09:14.218628+00:00
- HTTP: 200
- Risk score: 0
- Risk level: low
- Model: deterministic-v2

Subsequent Discovery reused the assessed risk state.
A fresh automatic reassessment of a stale risk state was
not independently demonstrated in the final acceptance.

## 6. Compliance transaction incident and correction

Observed infrastructure incident:

- Both Governance API replicas became unhealthy.
- Caddy returned HTTP 503 because no upstream was available.
- PostgreSQL remained operational.
- 80 database connections were waiting on locks.
- 9 sessions were idle in transaction.
- Oldest observed transaction exceeded 51 minutes.

Source inspection established an application-level self-blocking
path:

1. assess_if_needed acquired an application row lock.
2. Dynamic compliance opened an independent connection.
3. CTRL-07 invoked the publication guard.
4. The publication guard attempted to lock the same application
   through another connection.

Corrective implementation:

- Pass the existing transaction through compliance evaluation.
- Borrow that transaction in the publication guard.
- Preserve mandatory publication row locking.
- Isolate optional review database errors using a savepoint.
- Preserve independent transaction handling for standalone calls.

Automatic Discovery was paused while both API replicas were
recovered. Their uncommitted transactions were released.

No volumes were deleted and no PostgreSQL restart was required.

## 7. Regression and deployment verification

Targeted regression suite:

- 135 tests passed.
- Zero failures.
- One non-blocking Starlette deprecation warning.
- Includes two compliance transaction lifecycle regression tests.
- Includes three risk connection lifecycle regression tests.

Corrected Governance API image SHA256 values:

Replica A:
d5a092b56b56f42434ddaf54de358dbcdea99a89ee527ec4320945e8e1fe6958

Replica B:
b01592e5da9f5fff026e74ccf4c1e3b4d22db4da4d1742474149100084633ea0

All ten deployed source hash comparisons matched.

Verified:

- Both API replicas healthy.
- Health endpoint HTTP 200.
- Inventory endpoint HTTP 200.
- Dynamic compliance endpoint HTTP 200.
- Controlled isolated-fixture Discovery completed.
- CTRL-07 positive acceptance completed.
- Zero blocked connections after controlled acceptance.
- Zero idle transactions after controlled acceptance.

## 8. Automatic Discovery restoration

Automatic Discovery was restored on 2026-11-21.

Completed cycles started at:

- 2026-11-21T08:27:24.915336+00:00
- 2026-11-21T08:28:26.800513+00:00

Each cycle reported:

- Discovered: 9
- Known: 9
- Shadow: 0

Six operational samples, approximately 15 seconds apart:

- API HTTP 200 in every sample.
- Zero blocked connections in every sample.
- Zero idle transactions in every sample.
- Zero prolonged transactions in every sample.

Final inventory endpoint: HTTP 200.

Final health verification:

- Governance API load balancer: healthy
- Governance API A: healthy
- Governance API B: healthy
- PostgreSQL: healthy
- Automatic Discovery: healthy
- Appsmith governance proxy: healthy

These are bounded runtime stability observations, not a
long-duration availability or load-testing guarantee.

## 9. Retained assurance limitations

- Native manual publication enforcement was demonstrated in
  the isolated patched Appsmith environment.
- Universal interception of all native configuration and
  deployment paths is not established.
- Live Git publication was not tested.
- Integration-dependent security scanning requires complete
  supported connector evidence.
- Historical DLP events do not establish universal egress coverage.
- CTRL-06 verification is scoped to the observed proxy denial.
- CTRL-07 depends on current evidence and authenticated review.
- Compliance persistence uses result-based idempotency rather
  than independent source-evidence version tracking.
- The changes_last_24h feature remained null for the isolated
  fixture; missing temporal telemetry was not invented.
- The final stability check was bounded, not continuous load testing.
- Production certification, HA/DR qualification and universal
  enterprise enforcement are outside this acceptance.

## 10. Final disposition

LO2.1: Scoped policy-as-code acceptance complete.
Broader configuration and publication-route coverage remains partial.

LO2.2: Verified for observed Appsmith workflow changes and
the demonstrated insecure HTTP integration.

LO2.3: Scoped functional acceptance complete, including separate
positive CTRL-06 and CTRL-07 results.
Broader enforcement and evidence-version coverage remains partial.

LO2 corrective implementation and planned acceptance work are closed
at the documented MVP boundary.

No additional LO2 capability is introduced by this closure record.
Proceed to the existing LO3 requirement-level gap assessment.

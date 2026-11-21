# CR-002 — LO2 Native Publication Acceptance

Date: 2026-11-21
Scope: Isolated, patched Appsmith CE v2.2 environment.
Upstream Appsmith baseline: d847cf4.

## Application identity

- Application: LO2 Isolated Publish Fixture
- Governance ID: ee0752ad-17e1-466f-92bc-6bbe2108f173
- Native ID: 6affb740b82ed4d1f79df9fb

## Release A — Authorized publication

- Release digest:
  0b01d4ccd3393af8b57d098845b747e8d363b934a2719cc9bdb75bc408766a59
- Governance decision:
  f2027f2d-a721-4830-bfa3-393d3b1c6951
- Approval:
  d5493f84-655e-47fc-9607-a2e157ef7f42
- Verified reviewer policy: lcnc-security-reviewer
- Mandatory training: completed
- Observation:
  bf5b0695-eb86-463f-b549-716026ed9edd
- Governance preflight: HTTP 204
- Preflight receipt:
  cd1774cf-6b0b-4ae7-96ad-e45f692074d6
- Native publication: HTTP 200, success=true
- Native request:
  53135635-b170-47cc-a5ef-36bdadb87e90

Published page layout SHA-256:
3bc20bbcee21508c8e759e05b2f93c9f711d56d09c4d02227414150d220d48fa

## Release B — Rejected publication

Modification: Text widget containing LO2-UNAPPROVED-B.

- Modified release digest:
  129876d2d1b5b45140bdb5fbc55d926eb90c53a3606a9f49e16c2374198a99da
- Observation:
  662d2016-ecb3-480c-b4f2-b3169baf7bdb
- Automatic security rescan: passed, zero findings
- New governance decision:
  149250bb-f412-43c0-81a8-6c07c07dff5a
- Governance preflight: HTTP 403
- Denial receipt:
  8ab2f643-dbbd-488e-89b8-8cb964ebf53b
- Native publication: HTTP 403
- Native request:
  3409041e-b935-44cb-8bf2-68b56a611d8f

## Verified acceptance results

- Approved release A successfully published.
- Material draft modification detected.
- Automatic rescanning and governance evaluation triggered.
- Previous approval did not authorize modified release B.
- Native Appsmith rejected publication of B.
- Published page layout hash remained unchanged.
- Release B remained an unpublished draft.

The live rejection followed fresh discovery of B.
Commit-time digest mismatch and rollback were separately
demonstrated by Java integration tests.

## Remaining scope and limitations

- Manual native publication acceptance passed.
- Alternate release-route coverage remains to be finalized.
- Integration-dependent scanning coverage remains bounded
  by collected configuration evidence.
- CTRL-06 operation-level compliance correlation remains open.
- CTRL-07 recognition of current reviewed releases remains open.
- The reviewer workflow demonstrates authenticated role
  enforcement, not independent personnel separation.
- This checkpoint does not establish universal LCNC coverage,
  production readiness, or full LO2 acceptance.

## Native implementation version control

- Branch: audit/lo2-native-publish
- Source checkpoint: c43614b584bb708c0873110d6383c2df3ab2af56
- Repository: separate Appsmith lab checkout
- Distribution: local Git commit; remote publication pending

This source checkpoint preserves the native implementation.
It does not establish independent build reproducibility.

# Learning Objective Assurance Matrix

## Purpose

Map the six official learning areas and their 18 requirements to the
existing implementation, supporting evidence, verification results,
confirmed gaps and necessary remediation.

This review builds on the existing platform and previous audits.
It does not assume that previously implemented capabilities are missing.

## Reviewed Source Baseline

- Repository: hasnainops/lcnc-security-governance
- Baseline commit: 52f56ff439781552331f4a7c2119b2e8ae9aee58
- Baseline commit subject: chore(deps): update grouped Docker Compose dependencies
- Assessment branch: audit/learning-objective-assurance
- Existing requirement matrix: compliance/requirement-validation-matrix.md
- Existing evidence catalog: compliance/evidence-catalog.md
- Source-document review: complete
- Requirement-level implementation/evidence verification: pending
- Confirmed implementation gaps from this review: none established yet
- CR-002: not created

The source documents were read from the baseline commit. Their claims
are inputs to this assessment, rather than fresh runtime verification.

## Assessment Rules

1. Preserve the six official learning areas and all 18 requirements.
2. Distinguish documented claims, inspected implementation, tests and runtime evidence.
3. Reuse earlier evidence when its applicability to this baseline is established.
4. Record evidence provenance, source version and relevant limitations.
5. Distinguish implementation gaps from documentation or demonstration gaps.
6. Record production extensions separately from MVP requirement verdicts.
7. Do not add duplicate functionality or rebuild the platform without a confirmed need.
8. AI provides analytical signals; deterministic controls and accountable governance retain authority.

## Verdict Definitions

- PENDING: relevant implementation/evidence has not yet been checked in this review.
- FULL: sufficient applicable evidence supports the complete requirement within the stated MVP scope.
- PARTIAL: a specific part of the official requirement remains unmet or insufficiently demonstrated.
- MISSING: inspection confirms that the required capability is absent.

All 18 requirements below initially have verdict PENDING.
This does not invalidate earlier audit results.

## LO1 — AI-Driven Shadow IT Discovery and Application Inventory

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO1.1 | Deploy machine learning models for discovering unauthorized low-code/no-code applications. | Appsmith discovery, normalized enterprise ingestion, Isolation Forest and persisted ML evidence. | 1, 2, 15 | Trace source discovery through canonical inventory, ML analysis and Shadow IT candidate identification. Distinguish independently collected observations from manually submitted demonstration events. |
| LO1.2 | Implement automated application inventory with classification and risk scoring. | Application inventory, advisory ML classification, governed classification and deterministic risk assessments. | 1, 3, 5, 15 | Verify identity handling, automatic population, classification/risk orchestration, persistence and stale-evidence handling. |
| LO1.3 | Configure continuous monitoring for new citizen developer application deployments. | Appsmith discovery worker with a documented 60-second interval and discovery timestamps. | 1, 14, 15 | Demonstrate a newly created Appsmith application absent from the governance baseline being detected by the scheduled worker, with timestamps and inventory evidence. |

## LO2 — Automated Security and Compliance Validation

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO2.1 | Deploy policy-as-code enforcement for low-code/no-code platform configurations. | PARTIAL overall; scoped acceptance completed: OPA-backed release-bound native publication of approved A, denial of modified B, and proxy create/clone denial verified. | 6 | Universal configuration and publication-route interception is not established. Live Git publication remains unverified. See [Final LO2 acceptance record](evidence/CR-002-LO2-compliance-acceptance.md). |
| LO2.2 | Implement automated security scanning for citizen-developed applications and workflows. | VERIFIED for observed Appsmith workflow changes: automatic rescanning and persisted findings demonstrated, including SEC-009 detection and successful remediation. | 4, 15 | Integration-dependent coverage remains limited where connector evidence is incomplete. See [Final LO2 acceptance record](evidence/CR-002-LO2-compliance-acceptance.md). |
| LO2.3 | Configure compliance validation for data protection, access control, and integration security. | PARTIAL overall; scoped functional acceptance completed: seven controls, automatic assessment, persisted results, positive CTRL-06 and CTRL-07 acceptance on separate fixtures, and verified transaction lifecycle correction. | 10, 15, 19 | CTRL-06 uses privileged verification of an observed proxy denial. Universal DLP and access enforcement and independent source-evidence version tracking remain unverified. See [Final LO2 acceptance record](evidence/CR-002-LO2-compliance-acceptance.md). |

## LO3 — Risk-Based Governance and Approval Workflows

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO3.1 | Deploy intelligent risk assessment for citizen developer applications based on data sensitivity. | VERIFIED within observed MVP scope: six live risk scenarios, explainable deterministic scoring and persisted AI-assisted governance routing. | 2, 3, 5 | Cross-platform coverage and equivalent safeguards across all manual entry points are not established. See [Final LO3 acceptance record](evidence/CR-002-LO3-risk-governance-acceptance.md). |
| LO3.2 | Implement automated approval workflows with escalation for high-risk applications. | VERIFIED within MVP scope: automated routing, high-risk SLA escalation, reviewer authorization, training gates and mandatory BLOCK protection. | 5, 11, 15 | Consistent escalation latency and all reviewer assignment variants are not certified; senior decision authorization verified using isolated integration fixtures. See [Final LO3 acceptance record](evidence/CR-002-LO3-risk-governance-acceptance.md). |
| LO3.3 | Configure governance dashboards and risk analytics for executive oversight. | VERIFIED within deployed MVP scope: PostgreSQL-backed executive portfolio analytics, approval aggregation and browser acceptance. | 5, 14, 15 | Persisted MVP inventory and historical approval records are not a certified production portfolio or real-time review eligibility assessment. See [Final LO3 acceptance record](evidence/CR-002-LO3-risk-governance-acceptance.md). |

## LO4 — Data Loss Prevention and Access Control

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO4.1 | Deploy automated data classification and DLP policies for low-code applications. | ML advisory classification, authoritative stored classification, DLP inspection, effective sensitivity policy, strict fail-closed inspection response validation and metadata-only transfer audit evidence. | 3, 8, 9 | **VERIFIED — scoped governance MVP.** 23 focused tests passed; 6 deployed Gateway/DLP HTTP scenarios passed; 3 deployed malformed-response checks blocked; isolated Governance API-to-DLP audit acceptance and cleanup passed. See [CR-004 LO4.1 acceptance](evidence/CR-004-LO4.1-classification-dlp-acceptance.md). Universal platform routing, outbound execution and production certification are not claimed. |
| LO4.2 | Implement fine-grained access control and privilege management automation. | Vault-verified caller identity and role mapping; OPA action rules; authenticated JIT requests, approvals, grants, revocation, expiry and privilege audit events. | 7, 15 | **VERIFIED — scoped governance MVP.** 70 focused and compatibility tests passed; 16 live HTTP authorization checks passed; deployed JIT DENY/ALLOW/revocation/expiry lifecycle and persisted audit evidence verified. See [CR-003 LO4.2 acceptance](evidence/CR-003-LO4.2-access-privilege-acceptance.md). Universal LCNC platform enforcement and production certification are not claimed. |
| LO4.3 | Configure data exfiltration monitoring and prevention for citizen-developed integrations. | Integration Gateway, destination/transport restrictions, DLP fail-closed behavior and transfer evidence. | 9, 15 | Verify the protected integration path, server-owned trust inputs and prevention of outbound execution on BLOCK. Record the demonstrated routing boundary. |

## LO5 — DevSecOps Integration for Platform Management

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO5.1 | Deploy automated security testing integration with platform deployment pipelines. | Python/OPA tests, Trivy, SonarCloud and ZAP; governed image deployment; [verified LO5.1 evidence](evidence/lo5-1-ci-gate-acceptance.md). | 4, 13 | PASS within isolated CI/CD lab boundary: insecure change rejected, corrected change passed, vulnerable image blocked, CVE-2026-85091 remediated, approved deployment completed, image identity and health verified, post-deployment scan passed. Limits: comprehensive DAST, required branch checks and mandatory SonarCloud quality-gate enforcement remain unverified; integrated assurance revision not separately tested. |
| LO5.2 | Implement secrets management and secure credential handling for integrations. | Vault AppRoles, scoped policies, dynamic database credentials, file-delivered SecretIDs and managed Appsmith credentials. | 12 | Verify applicable evidence in compliance/evidence/objective14-secrets-management.md, including isolation, renewal, revocation and recovery. Preserve the static Appsmith password versus dynamic database credential distinction. |
| LO5.3 | Configure vulnerability management and security patching automation. | Trivy, Dependabot and the documented detection-to-remediation lifecycle. | 13; evidence catalog | Inspect compliance/evidence/objective15-vulnerability-remediation.md and current workflows. Identify automated stages, approval gates, redeployment and rescan evidence. |

## LO6 — Training and Secure Development Enablement

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO6.1 | Deploy automated security training delivery for citizen developers. | Control-triggered training assignments, subject/due-date tracking, completions, approval gates and training events. | 11, 16, 15 | Trace a control deficiency to an automatically assigned developer-visible training module, completion and retained evidence. |
| LO6.2 | Implement secure development guidelines and best practice enforcement. | Citizen Developer Secure Development Standard, targeted guidance, scanner/policy controls and approval gates. | 4, 6, 11, 16, 18 | Connect specific guidelines to their implemented enforcement and remediation behavior. |
| LO6.3 | Configure gamification and incentive systems for secure application development. | Evidence-based security score, Gold/Silver/Bronze/Needs Attention badges and training achievements. | 11, 16 | Verify the calculation and award conditions and demonstrate how qualifying security or training progress changes recognition. |

## Verification Record Format

For each requirement, record:

- requirement ID;
- inspected source paths and baseline applicability;
- test or runtime evidence reference;
- observed result;
- demonstrated scope and limitations;
- verdict and rationale;
- confirmed gap, if any;
- required fix and acceptance evidence, if applicable.

## Initial Reconciliation Notes

- Existing documentation already describes substantive LO6 functionality.
  Its presence must be checked before proposing additional training or gamification.
- The existing matrix has 20 project sections; its numbering does not
  correspond directly to the 18 official requirements.
- The existing matrix documents scanning rules SEC-001 through SEC-008.
  Current workflow-scanning coverage requires source/evidence inspection.
- ZAP is marked PARTIAL in the existing matrix, while later project history
  records successful runs. Establish applicability before changing the wording.
- API A/B failover is a demonstrated local resilience capability.
  Broader stateful-service and infrastructure HA remains a separate boundary.
- Generic enterprise-feed ingestion and independently collected Appsmith
  observations must retain their distinct provenance.
- Synthetic ML evaluation is not a production-accuracy claim.
- Appsmith-native access controls are separate from this platform's custom controls.

## Change-Control Handoff

After verification identifies specific gaps, prepare CR-002 with the affected
requirement IDs, evidence, proposed changes, security/architecture impact,
acceptance criteria and rollback approach.

Documentation or demonstration gaps may require evidence work without
application changes. No implementation remediation is approved by a PENDING
verdict alone.


## LO1 implementation checkpoint — 2026-11-11

This checkpoint updates the initial LO1 assessment only.
The remaining learning objectives retain their existing
review status until separately assessed.

| Requirement | Verified implementation | Acceptance status |
|---|---|---|
| LO1.1 — AI Shadow IT discovery | Live Appsmith discovery, automatic inventory registration, IsolationForest diagnostic anomaly assessment and persisted evidence | Demonstrated within Appsmith scope; broader acceptance pending |
| LO1.2 — Inventory, classification and risk | Automated inventory, deterministic risk scoring, connector provenance and synchronized field evidence | PARTIAL — automatic advisory classification and owner-context integration outstanding |
| LO1.3 — Continuous monitoring | Scheduled Discovery polling and detection of newly created applications and page changes | Demonstrated within Appsmith scope; sustained monitoring certification outstanding |

### Verified checkpoint evidence

- Live observations and application inventory synchronized in PostgreSQL.
- Source observation IDs and evidence provenance validated.
- Field evidence coverage distinguishes partial from none_observed.
- Existing owner-declared data fields remain untouched.
- IsolationForest diagnostic assessments and risk reassessment observed.
- Targeted LO1 regression suite: 80 passed, 0 failed.
- Discovery, Governance API instances and PostgreSQL healthy at final live check.

### Remaining LO1 acceptance gaps

1. Automatic advisory ML classification remains unverified end to end.
2. Business-purpose declaration, authentication and attestation provenance remain incomplete.
3. Dynamic Appsmith bindings do not yet establish verified field identities.
4. Broader LCNC platform coverage and sustained monitoring evidence remain unproven.
5. Final integration and acceptance against the official requirements remain pending.

These gaps are deferred, not waived. This is an implementation
checkpoint, not full LO1 sign-off.


## LO1 Appsmith MVP acceptance — 2026-11-17 UTC

This dated verdict supersedes earlier LO1 checkpoint status within the Appsmith
reference-platform MVP. Other learning-objective verdicts remain unchanged.

| Requirement | Verdict | Evidence |
|---|---|---|
| LO1.1: ML shadow IT discovery | FULL within stated MVP scope | Live collected configuration, persisted anomaly assessment and unregistered shadow candidate |
| LO1.2: Automated inventory, classification and risk | FULL within stated MVP scope | Automatic intake, attested owner context, automatic advisory classification/reassessment and risk scoring |
| LO1.3: Continuous monitoring | FULL within stated MVP scope | Before-creation absence, scheduled first discovery and subsequent observations/configuration updates |

See [LO1 acceptance and limitations](evidence/CR-002-LO1-Appsmith-acceptance.md).
Production accuracy, publication-event telemetry and cross-platform coverage
are not asserted. Low-confidence human review remains required.

## LO2 Appsmith manual publish denial checkpoint — 2026-11-18 UTC

LO2.1 remains PARTIAL. An authenticated POST to the canonical Appsmith
manual-publish endpoint through the installed proxy received formatted HTTP 403;
the decision ID matched a persisted deny receipt. The operator also observed
the native Deploy denial message in the browser. See
[scoped publish-denial evidence and remaining coverage](evidence/CR-002-LO2-Appsmith-publish-denial-checkpoint.md).

The browser screenshot cannot be paired to the API receipt, Appsmith omitted
the deployment timestamp from the tested inventory response, and other
configuration and publish paths have not been accepted. LO2.2 and LO2.3
retain the preceding verdicts and limitations.

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

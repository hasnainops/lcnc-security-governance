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
| LO2.1 | Deploy policy-as-code enforcement for low-code/no-code platform configurations. | OPA governance policy, policy tests and fail-closed mandatory authorization. | 6 | Identify the configuration facts evaluated, the enforcement point and applicable ALLOW/DENY/dependency-failure evidence. |
| LO2.2 | Implement automated security scanning for citizen-developed applications and workflows. | Citizen Application Security Scanner and persisted findings. | 4, 15 | Verify application and workflow observation coverage and automatic invocation. Separate citizen-application scanning from scanning the governance platform's own repository. |
| LO2.3 | Configure compliance validation for data protection, access control, and integration security. | Seven dynamic controls with pass/fail/not-assessed states and stored assessments. | 10, 15, 19 | Map each required protection area to its control inputs, evaluation and retained evidence; verify incomplete/stale evidence handling. |

## LO3 — Risk-Based Governance and Approval Workflows

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO3.1 | Deploy intelligent risk assessment for citizen developer applications based on data sensitivity. | Explainable deterministic risk, governed sensitivity and advisory ML evidence. | 2, 3, 5 | Verify sensitivity-dependent scoring and the actual effect of ML evidence on prioritization or governance routing. |
| LO3.2 | Implement automated approval workflows with escalation for high-risk applications. | Automated routing, approval requests, required roles, SLA escalation, human decisions and hard-block protection. | 5, 11, 15 | Trace automatic approval and high-risk review/escalation; verify training gates and rejection of attempts to override mandatory blocks. |
| LO3.3 | Configure governance dashboards and risk analytics for executive oversight. | Governance Portal, Grafana, risk assessments and workflow evidence. | 5, 14, 15 | Verify that displayed risk and governance information supports oversight and is distinguished from service-health metrics. |

## LO4 — Data Loss Prevention and Access Control

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO4.1 | Deploy automated data classification and DLP policies for low-code applications. | ML classification suggestions, authoritative classification, DLP inspection and transfer policy. | 3, 8, 9 | Trace classification and inspection into effective sensitivity and transfer decisions, including uncertainty and safe audit evidence. |
| LO4.2 | Implement fine-grained access control and privilege management automation. | OPA action rules, JIT requests/grants, automatic expiry, revocation and privilege audit events. | 7, 15 | Verify permitted/denied actions and the JIT lifecycle; explicitly document how caller identity and roles are established in the MVP. |
| LO4.3 | Configure data exfiltration monitoring and prevention for citizen-developed integrations. | Integration Gateway, destination/transport restrictions, DLP fail-closed behavior and transfer evidence. | 9, 15 | Verify the protected integration path, server-owned trust inputs and prevention of outbound execution on BLOCK. Record the demonstrated routing boundary. |

## LO5 — DevSecOps Integration for Platform Management

| ID | Official requirement | Current documented implementation | Existing matrix sections | Verification needed |
|---|---|---|---|---|
| LO5.1 | Deploy automated security testing integration with platform deployment pipelines. | Python/OPA tests, SonarQube, Trivy and ZAP workflow configuration. | 4, 13 | Link pipeline configuration to applicable successful runs and source commits. Reconcile older PARTIAL DAST wording with recorded execution evidence. |
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

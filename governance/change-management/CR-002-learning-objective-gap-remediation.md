# CR-002 — Learning Objective Gap Remediation

## Status and baseline

- Status: IN PROGRESS — response validation unit-tested; remaining implementation and validation pending.
- Created: 2026-11-04.
- Source baseline: 52f56ff439781552331f4a7c2119b2e8ae9aee58.
- Working branch: audit/learning-objective-assurance.
- Assurance register: compliance/learning-objective-assurance-matrix.md.
- This record does not change requirement verdicts or assert acceptance.

## Purpose

Complete the discovery-to-assessment flow within the existing local MVP:
automatically collect available technical facts, obtain accountable
owner-provided business context, and automatically perform and refresh
eligible assessments.

Appsmith remains the live reference platform. The existing normalized
enterprise feed remains an additional ingestion route.

## Learning-objective traceability

Primary requirements:

- LO1.1: Deploy machine learning models for discovering unauthorized
  low-code/no-code applications.
- LO1.2: Implement automated application inventory with classification
  and risk scoring.
- LO1.3: Configure continuous monitoring for new citizen developer
  application deployments.

Dependent verification includes security scanning, compliance, risk
governance, classification/DLP, approval workflows and training.
All six learning areas and all 18 requirements remain in the assurance
register; this change does not establish their completion.

## Findings supporting this change

1. Runtime evidence supplied on 2026-11-03 shows LCNC Governance Demo
   and Expense approval remaining pending for anomaly analysis and
   classification because required metadata is missing.
2. Appsmith discovery collects aggregate workflow-security counts,
   but those counts do not supply the five required anomaly count
   fields or the required classification content.
3. The Appsmith discovery pipeline invokes anomaly analysis,
   classification and scanning. It does not invoke risk assessment
   or the governance workflow.
4. Enterprise discovery attempts canonical inventory handoff only
   after successful ML analysis. Pending or failed ML therefore
   prevents that handoff.
5. The inspected enterprise handoff updates application facts without
   invalidating dependent risk/governance assessments. Observed
   workflow updates invalidate scanner results only.

Source evidence:
- discovery/appsmith_discovery.py
- enterprise-discovery/app/main.py
- governance-api/app/enterprise_handoff.py
- governance-api/app/workflow_evidence.py
- governance-api/app/workflow.py

Source findings refer to the baseline above. Runtime observations are
user-supplied evidence; deployed-image correspondence to that baseline
has not yet been independently verified.

## Proposed implementation

1. Define a field contract specifying meaning, source, observation
   time, collection completeness and unavailable-data behavior.
2. Collect technical metadata that Appsmith can reliably expose.
   Keep owner-supplied business purpose and data descriptions
   identifiable as owner-supplied information.
3. Persist discovered inventory independently of ML availability.
4. Run eligible assessments automatically through existing services,
   including the existing risk/governance workflow and its approval
   and training integration.
5. Invalidate affected results when their inputs change. Reassess
   changed inputs and retry eligible pending work without creating
   duplicate applications or repeated approval/training side effects.
6. Expose pending, failed, stale and assessed states with sufficient
   evidence to explain each outcome.

## Data and security constraints

- Unknown telemetry must not be converted to zero or false.
- Action count is not automatically connector or integration count.
- External destinations need an explicit internal/external definition.
- Approval status must come from governance evidence.
- changes_last_24h requires a reliable event source or sufficient
  observation history. A partial observation window is not a full day.
- If a required feature cannot be obtained reliably, document the
  limitation. Any model-feature change needs explicit rationale,
  retraining and evaluation before adoption.
- Separate authorization/registration evidence from ML anomaly results.
- Keep ML advisory and preserve governed classification, mandatory
  OPA controls, approval restrictions and training gates.
- Persist sanitized evidence; exclude raw credentials, tokens and
  unnecessary sensitive application content.

## Acceptance criteria

- A newly created Appsmith application enters inventory automatically.
- Inventory ingestion continues when ML is unavailable.
- Missing metadata produces explicit pending states and missing-field
  reasons, without fabricated measurements.
- Supplying verified technical facts and owner context automatically
  triggers the applicable analysis and governance steps.
- An anomaly result and authorization evidence are independently
  visible and traceable to the application.
- Changed inputs invalidate affected results and cause reassessment.
- Repeated unchanged observations do not duplicate inventory or
  approval/training side effects; eligible failures can recover.
- Existing mandatory policy, DLP, access, approval and training
  protections pass relevant regression checks.
- Runtime evidence records source identity, observation time,
  assessment/model version and resulting decision.
- The assurance register records evidence and remaining limitations;
  requirements are accepted individually after verification.

## Validation plan

Use focused tests for metadata mapping, missing/partial observations,
ML failure, retries, freshness and duplicate prevention.

Then demonstrate a real new Appsmith application progressing from
discovery through enrichment and assessment, including a controlled
failure-and-recovery case. Reconcile the resulting evidence against
all 18 requirements before final exam-readiness acceptance.

## Change and rollback controls

Document affected files, schema changes and deployment steps before
implementation. Prefer additive schema changes that preserve existing
records and assessment history.

Record the previously working application image versions before
deployment. Define rollback for the actual implementation, including
schema compatibility. Do not delete database volumes or audit evidence
as a rollback method.

## Completion evidence

Pending:
- Metadata field contract and source feasibility.
- Implementation diff.
- Focused and relevant regression-test results.
- End-to-end runtime evidence.
- Updated assurance verdicts and evidence catalog.
- Acceptance decision and residual limitations.

## Implementation progress

- Response-validation increment: 22 focused tests passed in the user's
  checkout; live deployment validation remains pending.
- Metadata contract: [CR-002-metadata-contract.md](CR-002-metadata-contract.md).
- Existing server-owned external-host allowlist identified for reuse.
- No learning-objective acceptance verdict is changed by this progress.


## LO1 implementation checkpoint — 2026-11-11

**Transition decision:** Freeze additional LO1 feature development
and begin LO2 after committing the verified checkpoint.

**Live verification completed:** Appsmith discovery, diagnostic
IsolationForest assessment, risk scoring, observation history,
connector provenance, field-evidence synchronization and
source-observation linkage.

**Regression evidence:** 80 targeted tests passed.

**Deferred LO1 gaps:**

- End-to-end automatic advisory ML classification.
- Authenticated business-purpose and owner-attestation provenance.
- Field identities unresolved within dynamic bindings.
- Sustained monitoring and broader LCNC coverage evidence.
- Final cross-objective integration and acceptance.

**Governance:** These gaps remain open under CR-002 and must
be reconciled during dependent LO work and final MVP acceptance.
No requirement is considered waived or fully accepted by this
checkpoint.

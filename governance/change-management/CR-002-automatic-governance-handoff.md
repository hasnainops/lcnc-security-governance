# CR-002: Automatic governance handoff

## Confirmed problem
For the independently discovered app fc05339a-c10c-4140-b3da-062f111aa65e,
classification and current-configuration inference were persisted, but governance
was stale and both governance_decisions and approval_requests were empty.
Discovery invoked assessment services but never governance. The existing
workflow did not consume the advisory classification review flag.

## Changes
- Discovery calls a new idempotent governance endpoint after its assessment pipeline.
- Governance locks the application and evaluates risk (if stale) and current OPA
  policy using the same database transaction. OPA is consulted on each call.
- Low-confidence classification and incomplete classification/scanning/AI evidence
  require Security/GRC review. OPA BLOCK retains precedence. No advisory result
  changes authoritative classification.
- Semantic input fingerprints reuse unchanged decisions. A policy result change
  creates a new decision. Poll times and observation IDs do not create duplicates.
- Persisted decisions retain source observation and classification-input provenance.
- Training and approval delivery occur after commit and retry on subsequent cycles.
  Training assignment failure holds routing and marks governance stale.
- Approval routing serializes by application; human actions reject superseded,
  stale or non-current Appsmith decisions. Existing hard-block and training gates remain.
- Classification state changes invalidate governance immediately.

## Migration and deployment
Apply 024_automatic_governance_handoff.sql before new API images start. It adds
nullable columns to an existing table and does not fabricate historical evidence.
Build governance-api-a, governance-api-b, governance-automation and discovery.
Stop Discovery during rollout. Recreate approval service and API replicas, then
Discovery, using existing credential-maintenance practices. Do not restart Vault
or PostgreSQL. Preserve previous image tags and run database backup procedures.

## Verification
Local regression: 475 passed, 6 dependency/deprecation warnings, 3 subtests.
Python 3.12 and PostgreSQL 16 in an isolated test database. External HTTP risk/OPA
responses are explicit test fixtures. Tests execute the actual approval routing
and human-decision function bodies against PostgreSQL. The Docker test recipe
includes the new tests for the user's PostgreSQL 18 environment.
The source upload omitted database/init.sql and unrelated service directories;
unchanged copies from the preceding workspace were used only to run regression
checks and are NOT included in this patch.

Live acceptance is pending:
1. Let scheduled Discovery process the existing fresh app; do not manually POST
   governance evaluation to claim automatic acceptance.
2. Verify a SECURITY_REVIEW decision with the classification review reason and
   a linked Security/GRC approval request. A mandatory policy BLOCK takes precedence.
3. Capture two unchanged polling cycles: same governance decision/request IDs.
4. Confirm changed evidence supersedes pending requests, and the actual reviewer
   can record a decision subject to existing training and hard-block gates.
5. Retain timestamps, input fingerprints, source versions and test results in the
   assurance matrix before advancing requirement verdicts.

## Boundaries and remaining work
This patch connects assessment to governance routing; it is not full LO1–LO6 sign-off.
Current app remains an empty prototype. Nonempty integrations, real business
workflow acceptance, classification approval/authoritative-label editing and
runtime recovery still require their own applicable evidence. The existing local
human-decision API accepts an actor string; this patch does not add SSO or prove
reviewer identity/role authorization. Polling is near-real-time, not instantaneous;
HTTP calls add cycle latency. Four-feature snapshot duplication after owner
context invalidation is unchanged and remains a separate optimization.

The endpoint consults current OPA before making/reusing a decision, but this is
not Appsmith deployment interception or universal request enforcement. A failed
poll cannot guarantee immediate invalidation of every existing UI view. Human
review verifies source freshness and application governance state; it does not
perform another policy evaluation at the moment of clicking approve.

## Rollback
Stop Discovery, restore tagged previous images for the four changed services and
restart them in dependency order. Nullable added columns can remain for audit
history and compatibility. Do not drop history or revert unrelated LO1/LO2 work.

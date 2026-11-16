# CR-002 — Classification recovery without duplicate inference

Checkpoint: 2026-11-14. This change does not grant full LO1 acceptance.

## Confirmed problem

Live evidence showed seven classification assessments with the same input
hash, owner-context ID, model digest and prediction. Six repeat assessments
followed observation gaps longer than the 180-second freshness limit.
The current source/model gate correctly withheld stale results, but cleared
the current input hash. Recovery checked only current state and therefore
ran inference again instead of reusing an immutable assessment.

## Change

After validating fresh owner/source inputs and fetching current ML identity,
the classifier holds the application row lock, respects any active inference
lease, and looks for a historical assessment with the same application and
complete input/model key. It validates the stored result, payload, model
identity, threshold and timestamp before reusing it. Invalid or incompatible
history falls back to the existing guarded inference path.

Recovery returns `action=revalidated`. It retains the original inference
timestamp, assessment ID and immutable history. Current provenance records
the fresh observation, the reused assessment, its original inference
observation, and a separate revalidation timestamp. Review reasons are
recomputed from current evidence and thresholds; prior required review is
preserved. Authoritative classification remains governed separately.

Missing/stale observations and unavailable ML identity still withhold the
current suggestion. Changing semantic inputs, owner declaration, model digest
or review threshold produces a new assessment. Unchanged healthy polls still
return `unchanged`. The seven existing live rows are not deleted or rewritten.

The read-only verification script now reports sanitized revalidation
references separately from immutable assessment history. No schema changes,
new privileges, model changes or history deletion are required.

## Verification

- The pre-fix implementation fails the recovery regression by returning a new
  `assessed` result instead of `revalidated` after an unchanged-source outage.
- Available root suite: 403 passed, zero skipped, 6 warnings, 3 subtests passed.
- Actual PostgreSQL 16.2 tests include 13 new regression cases: repeated source
  outages, model-health recovery, changed fields/purpose/model/threshold,
  concurrent recovery, invalid stored results, low-confidence review,
  active leases, and rollback/retry after a failed restoration write.
- Syntax and git whitespace checks pass. The incremental patch is checked
  against the exact pre-change files, preserving unrelated work.
- The user's additional uncommitted LO2 code is not present in this preparation
  checkout. Run the full local suite and isolated PostgreSQL 18.4 Compose suite
  before deploying. Those suites do not establish live acceptance by themselves.

## Deployment and live acceptance

Apply the incremental patch after the previously delivered name-sync patch.
Use `git apply --check` first; do not reset local changes to force application.
Run root tests and `compose.lo1-test.yml` in the isolated `lcnc-lo1-tests`
project. Then build and recreate only Governance API A and B, preserving image
references for rollback and using `--no-deps --no-build --pull never` for rollout.
Discovery already handles any `assessed` response status and logs the action;
it does not need a rebuild for this change. Preserve Vault and its in-memory
configuration, Appsmith and PostgreSQL.

For live acceptance, retain history count and latest assessment ID, show that
stale source evidence withholds classification, then resume fresh identical
observations. Expect `revalidated`, unchanged assessment count/ID/inference
timestamp, and updated revalidation evidence. Exercise a genuine input change
separately and expect a new assessment. Do not deliberately interrupt service
until the baseline and a recovery procedure are ready.

Rollback uses the prior API images; this additive code change has no schema
rollback. Keep all historical evidence.

## Remaining gaps

This patch does not correct all-or-nothing anomaly feature persistence. Recent
complete observations establish zero configured connectors/actions, while the
five canonical feature columns remain NULL until the full vector is eligible.
Persisting field-specific evidence independently needs a separate compatible
change to the ingestion code, which also contains the user's LO2 work.

The observed gaps prevent continuous 24-hour change coverage; unknown history
must not be replaced by zero. The cold-start diagnostic path requires witnessed
structural changes and is not a certified 24-hour assessment. This patch does
not manufacture anomaly results or implement the empty app's expense workflow.
It does not establish the cause of collection gaps (for example laptop sleep,
service interruption or connectivity), or claim instantaneous monitoring.

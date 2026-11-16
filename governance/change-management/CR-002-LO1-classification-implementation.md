# CR-002 — Automatic classification and owner context

Implementation checkpoint: 2026-11-12. Live acceptance remains pending.

This increment addresses the LO1.2 classification/owner-context gap on
`audit/learning-objective-assurance`, starting from `5e511cd` and the accepted
classification-freshness guard. It does not replace the six learning areas,
their 18 requirements, or the existing LO2 remediation. The project owner
authorized implementation in the conversation. No overall LO1 FULL verdict
is asserted by this change.

## Resulting flow

1. A citizen developer creates or changes an application in Appsmith.
2. Existing scheduled discovery independently registers/updates inventory,
   observations, feature evidence and risk. Registration remains unregistered
   until a governed action changes it.
3. A local operator assigns an application-scoped credential to the accountable
   owner. The owner supplies a business purpose and schema descriptions through
   the portal, authenticated with that credential.
4. Saving the declaration invokes classification automatically. Scheduled
   discovery also reconciles classification, using current database evidence
   instead of its older inventory snapshot. Missing prerequisites remain pending.
5. The existing ML model returns an advisory suggestion. Assessment inputs,
   model digest, owner declaration and observation references are persisted.
   Risk/scanning continue through the existing discovery pipeline; changed
   owner facts invalidate their prior results for reassessment.
6. The portal displays freshness-aware classification. Human review requirements
   are visible. This increment does not create a new approval engine or make
   the AI suggestion authoritative; automatic LO3 approval/escalation acceptance
   remains a separate verification task against the existing workflow.

Discovery uses its configured polling interval (currently 60 seconds) plus
cycle duration, not an instantaneous event stream. Owner submission initiates
classification immediately. The owner page refreshes status every 5 seconds;
the governance classification card refreshes every 10 seconds. Observations
older than 180 seconds are ineligible. Measure actual latency in the live test.

## Identity, evidence and failure behavior

- Operator-issued random bearer credentials are scoped to one application,
  expire within 1–30 days and support revocation. Only SHA-256 digests are stored
  in PostgreSQL. The credential file is created with mode 0600; the browser keeps
  its token in memory and sends it only as an Authorization header.
- This is an explicitly bounded local MVP identity mechanism. It records the
  operator's assignment of a named subject; it does not claim Appsmith session
  identity, mailbox verification, SSO/MFA or an enterprise identity provider.
  Use the loopback portal. Remote deployment would need HTTPS and the project's
  broader identity/access-control design.
- Owner name, email and subject come from the operator-issued credential,
  never from caller-supplied declaration fields. Existing generic application
  PATCH fields do not establish attestation or replace immutable owner context.
- The API can SELECT credentials but cannot issue, edit or revoke them. Owner
  declarations and classification history receive SELECT/INSERT grants only.
  Submission and the operator revocation helper share a transaction-scoped
  advisory lock. Expiry/revocation blocks future submissions; a declaration
  validly accepted earlier remains historical evidence.
- Owner declarations and observed widget fields/destinations remain distinct
  in `source_evidence`. Dynamic bindings do not become verified field schemas.
  Partial connector observations remain partial and require review. Action
  counts are never substituted for connector counts, and no absent ML feature
  is fabricated as zero.
- URLs supplied to classification contain only sanitized scheme, host and
  optional port. No headers, credentials, request bodies, query strings or
  actual sensitive records are required by this flow. Owner descriptions must
  describe the schema, not contain record values.
- Inference occurs outside a database transaction. A 90-second lease avoids
  duplicate concurrent work; an expired lease is retryable. Inputs are checked
  again under the application lock before history and current result commit
  together. Changed inputs, model identity or threshold reject an old response.
- The input key excludes polling timestamps and observation IDs, but includes
  semantic observations, the declaration version, model bytes/version and
  review threshold. An unchanged poll does not add another assessment.
- Missing/stale evidence, unavailable ML and invalid responses are explicit
  pending states. Inventory and the owner declaration survive ML failure. Old
  assessments remain in history and are withheld from the current-status view.
- Existing `/ml-classify` now delegates to this guarded flow. It can return an
  idempotent `unchanged` or explicit `pending` result with HTTP 200. Use the new
  `ml_classification_status` and `action` fields, not HTTP 200 as proof of an
  assessment. `/ml-classify-if-needed` is the scheduled endpoint.

## Model compatibility

The TF-IDF/logistic-regression artifact and its four input fields remain
unchanged. Provenance labels are stored outside model text because adding
those words changed a synthetic challenge prediction. New declarations still
change the text distribution; no production-accuracy claim follows from this.

The existing 20-row synthetic challenge set scored 20/20 with its original
inputs. The explicit owner-schema/action-host variant, using the new assembler,
scored 19/20. The mismatched payroll fixture had low model confidence and was
flagged for review; zero incorrect fixtures escaped either the model review
threshold or the combined review gate. All 20 variant fixtures had partial
connector identity evidence and therefore required review. This is a diagnostic
limitation, not 100% accuracy or permission to auto-approve sensitive data.

Confidential/restricted suggestions always require review, as required by the
existing classification schema. The authoritative `data_classification` is
unchanged. The checked artifact SHA-256 is
`ba36f63158480a1ce1004a2322c0cbd1fe1368d2934a85a898256041dfa54a95`.
The artifact records scikit-learn 1.9.0; repository requirements pin 1.9.1.
Testing with 1.9.1 retained the existing version warning. No dependency downgrade
or retraining was performed. Repeat the included diagnostic in the deployed
runtime and retain this compatibility limitation in acceptance evidence.

## Verification completed during preparation

- Focused contract, credential, source freshness and legacy freshness tests.
- Full available root Python regression suite and portal JavaScript tests.
- Actual PostgreSQL 16.2 single-backend SQL/transaction tests, including owner
  submission, idempotency, competing request leases, changed-source rejection,
  failure/recovery, stale display, rollback and least-privilege grants.
- ML service tests and the existing model artifact compatibility diagnostic
  using the pinned scikit-learn 1.9.1 runtime.
- Python/JavaScript/shell syntax and `git diff --check`.

The exact run totals are included in the delivered package's README. A normal
multi-session PostgreSQL server was unavailable in the preparation environment;
the simultaneous-connection test is supplied in `compose.lo1-test.yml`. The
user's uncommitted LO2 files and live Docker containers were not directly
available here. Their regression and runtime results must be collected before
acceptance. No migration or deployment has been performed on the user's Mac.

### Runtime follow-up — 2026-11-13: source names and baseline ordering

The user verified the five-service rollout and captured a 17-record baseline
around 14:52:41 UTC. Inventory inspection subsequently showed an Appsmith record
first discovered at 14:51:40 UTC as `Untitled application 1`, with its heartbeat
still advancing. A name-filtered check returned no match. The supplied editor
page must be matched through persisted page IDs before claiming it is that
record. The preexisting record cannot demonstrate absence from this baseline.

Inspection confirmed that the known-application path refreshed timestamps but
did not synchronize an Appsmith rename. The collector now sends only the source,
external application ID and current name to the existing `/seen` endpoint.
The API updates the name only when source and external ID match the canonical
record. Empty-body callers retain the previous heartbeat behavior. No owner,
registration, classification, risk or approval authority is accepted in this
payload. The existing endpoint's local collector trust boundary is unchanged;
identity matching is not a new caller-authentication mechanism.

Migration 022 already invalidates advisory classification when the model's
application-name input changes. A repeated identical name does not invalidate
it or duplicate classification history. IDs, first-discovery timestamps,
owner attestations, authoritative classification and shadow-candidate evidence
are preserved. No new migration or model change is required by this fix.

The verification helper now uses the real `first_discovered_at` column. A new
read-only page-ID helper avoids relying on editable display names. It records
whether the source/application identity was already in the retained baseline;
it never changes that baseline or manually registers an application.

Preparation verification: 390 available root tests passed, zero skipped,
including the PostgreSQL 16.2 multi-session suite and five added SQL cases for
rename freshness, unchanged polling, legacy heartbeat and identity mismatch.
The updated disposable PostgreSQL 18.4 suite contains 107 tests. The user's
additional uncommitted LO2 tests and live rollout of this fix remain to be run.
LO1 remains partial pending the real owner/classification workflow and correctly
ordered new-application acceptance evidence.

## Installation and deployment order

1. Apply the compatibility-checked package without resetting or stashing the
   user's existing work. Run the full local root tests and portal tests.
2. Run the disposable database suite, isolated from the live project:

   ```bash
   docker compose -p lcnc-lo1-tests -f compose.lo1-test.yml up --build --abort-on-container-exit --exit-code-from lo1-tests
   docker compose -p lcnc-lo1-tests -f compose.lo1-test.yml down --volumes
   ```

   Record the first command's exit code before cleanup. No tests may be skipped
   in this dedicated setup. Its password is a disposable test fixture, its
   storage is temporary, and it publishes no ports. It does not mount the live
   application's volumes or credentials.
3. Review the working-tree diff and pending migrations together. Existing
   migrations 019/020 must be applied. The user's pending LO2 migration 021 must
   be handled under its existing change procedure before deploying those LO2
   code changes. Do not assume an untracked SQL file has executed in PostgreSQL.
4. Apply additive migration 022 using the existing database operator:

   ```bash
   docker compose exec -T postgres sh -eu -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/migrations/022_owner_context_classification.sql
   python3 scripts/configure-lo1-vault-grants.py
   ```

   The targeted Vault helper preserves existing role statements, TTLs and
   revocation settings. It adds SELECT for credentials and SELECT/INSERT for
   declarations. Future bootstrap also calls this helper. Do not run the full
   bootstrap or restart Vault as part of this increment.
5. Record current image IDs for rollback. Once schema and tests are verified,
   build/recreate only `ml-analytics`, `governance-api-a`, `governance-api-b`,
   `discovery` and `governance-portal`, with `--no-deps`. Preserve running
   Appsmith, PostgreSQL and Vault. The ML service must be updated for its model
   digest/review-threshold health contract. Recreated API processes obtain new
   Vault database credentials with the new grants.
6. Issue a credential using real application and assigned owner identifiers:

   ```text
   python3 scripts/issue-owner-context-credential.py --application-id APPLICATION_UUID --subject-id ASSIGNED_SUBJECT --owner-name "ACTUAL OWNER" --owner-email ACTUAL_EMAIL
   ```

   These uppercase values are placeholders to replace, not values to invent.
   Open `http://127.0.0.1:3000/owner-context.html`, select the application, load
   the private file printed by the command, and enter factual purpose/schema
   descriptions. Do not upload the credential file into chat or Git.

   Revoke it with `python3 scripts/issue-owner-context-credential.py --revoke CREDENTIAL_UUID`.

## Live LO1 acceptance evidence still required

| Requirement | Demonstration and retained evidence |
|---|---|
| LO1.1 | Capture inventory before creating an Appsmith app. Create it outside Governance inventory; show scheduled discovery registering its independent Appsmith identity as unregistered, retaining the shadow candidate and running the existing ML anomaly path. Distinguish diagnostic/cold-start ML from fully evidenced historical features. |
| LO1.2 | Submit a real authenticated owner declaration. Show automatic advisory classification, observation/declaration/model references, unchanged authoritative classification and scheduled risk reassessment. Repeat an unchanged poll with no new assessment; change real fields/purpose and show reassessment. |
| LO1.3 | Retain creation, first discovery, observation, classification and risk timestamps over repeated scheduled cycles. Exercise a source/ML failure and recovery while inventory survives and current results are withheld when stale. Report measured latency and polling coverage. |

`python3 scripts/verify-lo1-classification.py` records a sanitized inventory
checkpoint. Add `--application-id APPLICATION_UUID` for classification and
assessment references. This tool is read-only and does not generate evidence
by manually invoking classification. Retain before/after output with the
relevant Git revision, dirty diff and container image IDs.

Broader LCNC platform coverage, complete dynamic-binding resolution, sustained
monitoring certification and all-objective end-to-end sign-off remain explicit
acceptance items. Do not silently waive them or relabel incomplete counts.

## Rollback

Before deployment, the package installer can restore only its own touched
files using its recorded backup, refusing to overwrite subsequent edits.
For a deployed rollback, first stop discovery, restore the previous compatible
API/ML/discovery/portal images and source, then restart those clients. Preserve
the additive tables/columns and retained history; do not drop the new schema
objects or reset PostgreSQL/Vault as a routine rollback. Revoke any issued owner
credentials that are no longer needed. Recheck existing LO2 behavior separately.

## Predeployment verification checkpoint — 2026-11-13

The user reported 372 passing root tests, 18 database-test skips, five warnings
and three passing subtests. After correcting the disposable database fixture,
the dedicated Python 3.13/PostgreSQL 18.4 Docker run passed all 63 tests, with
one deprecation warning, no skips and exit code 0. Its database errors for a
forced write failure and prohibited credential update were expected negative
tests. The dedicated test project was then removed.

Live schema inspection found discovery observations and data-field evidence
present, with the owner-context/classification additions from migration 022
absent. No live classification acceptance follows from the isolated tests.

Compatibility inspection also reproduced an LO2 receipt-integrity defect in
migration 021: SQL CHECK permits UNKNOWN, allowing a forwarded receipt with a
NULL HTTP status. Migration 023 adds an explicit IS TRUE constraint while
retaining valid evaluation-only events. It changes no historical rows. An
invalid existing receipt aborts the migration and requires evidence review;
do not invent a response status to make it pass.

The extended isolated suite passed 86 tests on PostgreSQL 16.2, including 23
new checks for receipt states, repeated migration application and preservation
of invalid historical evidence when validation fails. The 86-test run must
also pass in the user's PostgreSQL 18.4 test project before live migration.

Apply migrations 021, 022 and 023 in order using the existing database
operator, then run the targeted LO1 Vault-grant helper. Preserve a database
backup and running image IDs. Rebuild/recreate only the planned application
services after schema and grant verification; preserve Vault, PostgreSQL and
Appsmith. LO1 runtime demonstration and LO2 acceptance remain pending.

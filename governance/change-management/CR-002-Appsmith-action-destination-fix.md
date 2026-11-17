# CR-002: Resolve query destinations through saved datasource references

## Problem and change

The live connector proof application has six saved datasources and eight
queries referencing them. Saved connector destinations are observed, but
sanitizing reference-only query records alone produces unresolved destinations.
Classification therefore reports `integration_destinations_unresolved` even
though the saved base destinations are available.

The collector now passes the successfully enumerated workspace datasources
into workflow observation collection. Static API queries can inherit a
sanitized destination from an exact saved datasource ID. Duplicate identities,
workspace conflicts, plugin conflicts, ambiguous stored environments, explicit
conflicting destinations, and dynamic or authority-bearing paths do not gain
a resolved destination. Null/empty reference configuration may use the saved
record; nonempty unresolved embedded configuration cannot be overwritten.
The existing raw-action sanitizer remains unchanged; callers without the
workspace enumeration cannot resolve a reference-only action on its own.

Only scheme, host and optional port enter destination evidence. Raw query
paths, headers, credentials, bodies and datasource configuration are not
persisted by this join. The query and saved datasource records are not mutated.

## Scope

- Depends on the earlier Appsmith datasource-storage fix.
- Rebuild and recreate discovery only; no database migration or API rebuild.
- Classification safeguards, model inputs/thresholds, authoritative
  classification, and destination approval policy are unchanged.
- Corrected observations change the classification semantic hash, allowing
  the existing automatic worker to reassess without another owner attestation.
- Static configuration evidence does not prove execution-time destinations,
  redirect targets, DLP enforcement, or full LO1 acceptance.

## Validation

Local repository tests: 492 passed, 106 skipped, 3 subtests passed; six
dependency deprecation warnings. Skipped integration tests are not claimed
as runtime validation. New tests exercise the real collection path, shared
datasource references, ambiguity handling, sanitization and classification
input hashing. The before/after classification test retains other review
reasons and demonstrates that resolving evidence does not alter model text.

Live verification is pending. For governance application
`20fe2957-f769-4faa-a23a-1fa28584c359`, preserve the prior evidence and collect
new classification and connector reports after a scheduled discovery cycle.
Expect six connectors, five unapproved integrations, a matching anomaly
assessment and a new classification assessment. For the static queries,
`integration_destinations_unresolved` should disappear. Low-confidence review
may remain and authoritative classification may remain unknown.

If rollout fails, retain the printed pre-build image tag. Restore that image
to the discovery build's original local image tag and recreate discovery.
The incremental patch can be reversed with `git apply --reverse --check`
followed by `git apply --reverse` when its hunks still match. Do not revert
unrelated work or rewrite historical evidence.

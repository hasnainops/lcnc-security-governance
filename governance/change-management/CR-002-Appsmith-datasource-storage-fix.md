# CR-002: Appsmith saved datasource storage parsing

## Observed failure

The live LO1 connector proof application (`20fe2957-f769-4faa-a23a-1fa28584c359`)
had one saved REST datasource referenced by a query. Appsmith displayed the base
URL `https://example.com`, but the connector verifier returned
`destination_unresolved`, a null host, three unknown destination counts and no
matching ML snapshot assessment.

A value-redacted authenticated datasource inspection showed the URL under
`datasourceStorages.unused_env.datasourceConfiguration.url`. The collector only
read top-level `datasourceConfiguration`. This is a collector compatibility bug;
executing a query or accumulating temporal history does not fix it.

## Change and boundaries

- Preserve the legacy top-level configuration format.
- Read configuration from exactly one datasource storage entry, after confirming
  that its `datasourceId` matches the enclosing saved datasource ID.
- Leave malformed, missing, mismatched, or multiple storage entries unresolved.
  The observation contract has no active-environment selection. Multi-environment
  support requires a separate explicit environment mapping; dictionary order is
  not evidence of which environment is active.
- When both formats contain a destination URL, require them to agree.
- Continue using the existing destination sanitizer: evidence contains scheme,
  host and optional port, never URL credentials, paths, queries or headers.
- Approval policy, DNS trust evaluation, snapshot scoring and temporal-history
  requirements are unchanged. No database migration is required.

## Verification

Synthetic fixtures reproduce the live response structure without real secrets.
Before the fix, the destination extraction and downstream feature-assembly tests
both failed with the same unresolved destination/unknown counts as the live app.
After the fix:

- Connector-policy and discovery-health tests: 67 passed.
- Available repository tests on Python 3.12: 462 passed, 106 skipped,
  6 dependency deprecation warnings, 3 subtests passed.
- Database-dependent tests were skipped in this run; this patch does not change
  database code or schemas.
- The downstream fixture uses mocked public DNS and an explicit approval policy;
  it proves known current-configuration counts with `changes_last_24h = null`.
  It does not establish live DNS reachability, an anomaly-positive case, or full
  LO1 acceptance.

## Rollout and live checkpoint

Apply the incremental patch after the connector-policy checkpoint, run tests,
retain the current discovery image under a rollback tag, build discovery and
recreate only discovery. Keep the existing proof application and saved query.
After a completed collection cycle, run:

```bash
python3 scripts/verify-lo1-connector-policy.py \
  --application-id 20fe2957-f769-4faa-a23a-1fa28584c359 \
  --expect-connectors 1
```

The next required evidence is `host: example.com`, known destination counts
according to real DNS/policy, and a matching persisted snapshot assessment.
Unapproved status must follow the configured approval policy. An anomalous result
is not required merely because there is one connector. Live verification remains
pending until the patched collector runs on the user's environment.

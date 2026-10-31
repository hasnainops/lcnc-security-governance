# CR-001: Bounded snapshot-read retry

## Problem
Both API replicas intermittently returned snapshot_missing.
Direct file sampling observed six ENOENT open failures roughly ten seconds
apart, matching the collector update interval. The underlying filesystem
cause remains unconfirmed.

## Change
Retry FileNotFoundError up to three attempts, with 50 milliseconds
between attempts. Persistent absence remains unavailable.
Other read errors and invalid data are not retried.
Existing snapshot validation and stale-data rules remain in place.
The collector's atomic replacement strategy is unchanged.

## Verification — 2026-10-21 UTC
- Platform-status and targeted retry tests: 44 passed; one deprecation warning.
- Comparison across seven snapshots:
  updated API A returned 1056 current responses without failure;
  unchanged API B returned 1054 current responses and two snapshot_missing responses.
- Both replicas subsequently deployed with the mitigation.
- Each replica passed an inventory read containing 14 applications.
- Final 60-second public-path check:
  Caddy returned 958 current responses across seven snapshots;
  Portal returned 958 current responses across seven snapshots;
  neither path reported failures.
- Previous replica images retained under:
  lcnc-governance-api-a:before-snapshot-retry-c60c216
  lcnc-governance-api-b:before-snapshot-retry-c60c216

## Limits
This mitigates the reproduced short visibility gaps; it does not establish
the filesystem root cause or guarantee recovery from longer gaps.
Complete unified solution workflow acceptance remains pending.

# CR-001: OPA functional policy evidence

## Change
Added six synthetic policy decision checks against the running OPA server.
Checks cover governance allow/deny, viewer export restrictions, matching
JIT permission, restricted-data protection and registration enforcement.
All six decisions must match their expected results to report Passed.

The probe has a three-second total deadline and bounded response sizes.
Reports expose counts and sanitized failure reasons.
The portal displays policy evidence separately from inventory counts
and Docker health, with independent timestamps and stale-data handling.

## Verification — 2026-10-22 UTC
- Existing OPA policy tests: 15 passed.
- Direct live HTTP decision checks: six passed.
- Backend probe and regression suites: 80 passed.
- Corrected test-loader suite: 16 passed without warnings.
- JavaScript model suites: 17 passed.
- DOM integration checks passed, including policy-case rendering,
  failure handling, unavailable reports and stale-count suppression.
- Both API replicas and the portal deployed successfully.
- Both replicas returned five successful functional checks.
- Portal proxy returned four inventory results of 14 applications each
  and OPA evidence of six out of six matched policy cases.
- Updated portal rendering script was served successfully.
- Manual browser appearance has not yet been verified for this change.

## Limits
Synthetic JIT input does not issue a grant or verify its approval,
expiry, identity provenance or enforcement by an application.
These six cases do not establish correctness for every possible input.
Fifteen services still have no configured functional probe.
Complete business-workflow acceptance remains pending.

## Rollback images
- lcnc-governance-api-a:before-opa-functional-3e8a4ac
- lcnc-governance-api-b:before-opa-functional-3e8a4ac
- lcnc-governance-portal:before-opa-functional-3e8a4ac

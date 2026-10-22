# CR-001: Inventory functional evidence

## Change
Added bounded inventory-read probes for both Governance API replicas,
Caddy and the portal proxy, exposed through /exam/functional-status.
The portal displays this evidence separately from Docker health.
Other services explicitly show functional checks as not configured.
Reports expose status and counts without application records or raw errors.

## Verification
- Backend functional, route and platform regression tests: 61 passed.
- JavaScript platform and functional model tests: 13 passed.
- DOM integration checks passed, including failed inventory while Docker
  health remains healthy, unavailable reports, recovery, local aging,
  withheld stale counts, selection races and text escaping.
- Both API replicas and the portal were deployed separately.
- Live probes returned 14 applications through all four inventory paths.
- Browser screenshots on 2026-10-22 UTC confirmed four Passed rows,
  independent functional timestamps and 16 Not configured rows.
- Screenshots showed local age advancement; automatic browser polling
  timestamp advancement was not separately confirmed.
- Rollback images retained:
  lcnc-governance-api-a:before-functional-checks-967cb6f
  lcnc-governance-api-b:before-functional-checks-967cb6f
  lcnc-governance-portal:before-functional-evidence-967cb6f

## Limits
Failure rendering was verified with mocked responses, without disrupting
live credentials or database access.
These probes establish inventory-read evidence, not complete business
workflow acceptance or functional coverage of every service.
Complete CR-001 acceptance remains pending.

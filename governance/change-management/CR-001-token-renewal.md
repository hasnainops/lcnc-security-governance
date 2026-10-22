# CR-001: Governance API token renewal

## Change
Renew the cached Vault token before requesting replacement database
credentials. Renewal rejection with HTTP 400/403 clears the cached token
and allows reauthentication. Transport/server failures propagate without
an additional login attempt. Cached database credentials avoid extra
renewal requests.

No Vault policies, credential lifetimes or use limits were changed.

## Verification — 2026-10-20
- Existing and added database tests: 17 passed.
- Git whitespace validation passed.
- API A and API B deployed separately; both read 14 applications.
- Live diagnostic renewal passed; token was renewable with 1199 seconds
  remaining. Diagnostic token was revoked afterward.
- Previous replica images preserved under:
  lcnc-governance-api-a:before-token-renewal-2937d54
  lcnc-governance-api-b:before-token-renewal-2937d54

## Remaining acceptance
- Renewal across a full live database-lease cycle remains unverified.
- Token maximum lifetime remains one hour; reauthentication is still needed.
- Secret ID expiry and use limits still require controlled maintenance.
- Automatic Secret ID rotation and lockout recovery are not implemented.
- This checkpoint does not establish complete CR-001 acceptance.


## Manual Secret ID rotation verification — 2026-10-21 UTC

- Governance API Secret ID had four remaining login uses and
  approximately 4.77 hours before expiry; its AppRole was unlocked.
- A fresh Secret ID was issued and the existing mounted file updated
  in place. No containers were restarted.
- Both API replicas continued returning inventories of 14 applications.
- Separate diagnostic logins from both replicas accepted the mounted
  Secret ID. Both diagnostic tokens were revoked successfully.
- Other workload credentials had 43 remaining uses and approximately
  4.87 hours before expiry at inspection; they were not rotated.
- No credentials were printed or added to Git.
- Reusable maintenance tooling and scheduled rotation remain pending.
- This verifies manual rotation, not long-term credential reliability.


## Controlled rotation verification — 2026-10-21 UTC

- Added explicit single-role rotation; default operation remains read-only.
- Rotation refuses locked roles and unavailable credential metadata.
- Selected workloads stop before the credential file is updated in place.
- Credential file inode is preserved for existing container mounts.
- Restart now targets existing container IDs directly.
- Initial Enterprise Discovery rotation saved its credential but failed
  during restart. Manual container start restored health; the original
  Compose restart failure remains unexplained.
- Revised start helper and mounted-credential verification passed live
  for Enterprise Discovery.
- Complete corrected rotation passed for Governance Automation:
  stop, issuance, file update, start, mounted-credential authentication,
  diagnostic token revocation, and subsequent health check.
- Automated validation: 10 rotation/helper tests and six reporting tests passed.
- Previous Secret IDs are retained until expiry or use exhaustion.
- Rotation is operator-invoked; scheduled maintenance is not implemented.
- Automatic lockout recovery remains disabled.
- API-pair and Appsmith Discovery rotation through this command remain
  unverified. Complete workflow acceptance remains pending.
- Runtime credentials are excluded from this commit.


## API pair and Appsmith rotation verification — 2026-10-21 UTC

- Corrected rotation command passed for appsmith-discovery.
- Its post-restart discovery cycle at 02:36:58 UTC completed with
  three known applications and zero shadow applications.
- Missing ML/classification metadata remains a separate application issue.
- Corrected rotation command passed for governance-api.
- Both API replicas accepted the mounted credential; both diagnostic
  tokens were revoked.
- Both replicas, Caddy and the portal returned 14 applications afterward.
- API rotation stops both replicas temporarily; zero-downtime rotation
  is not implemented.
- Enterprise Discovery recovered from the earlier restart failure and
  passed the revised helper and authentication checks; its complete
  corrected rotation sequence has not been rerun.
- Scheduled maintenance, automatic lockout recovery, intermittent
  snapshot_missing and dashboard functional evidence remain open.


## Scheduled threshold rotation evidence — 2026-10-22 UTC

- Background maintenance rotated governance-api at 10 remaining uses,
  with 3.60 hours remaining before expiry in the report.
- Enterprise Discovery rotated with 1.09 hours remaining and 41 uses.
- Governance Automation rotated with 1.27 hours remaining and 42 uses.
- Appsmith Discovery rotated with 1.29 hours remaining and 42 uses.
- All selected workloads passed mounted-credential authentication and
  diagnostic-token revocation.
- Enterprise Discovery completed the corrected full rotation sequence.
- Both use-limit and expiry-threshold selection were observed live.
- LaunchAgent inspection showed 48 runs and latest exit code zero.
- Subsequent metadata inspection showed all roles unlocked and not due.
- A report gap from 23:04 to 01:19 UTC was observed; its cause is
  unconfirmed. Uninterrupted five-minute execution is not established.
- Authentication verification does not establish complete workload
  functionality. Sleep/wake recovery and automatic lockout recovery
  remain unverified or unimplemented.

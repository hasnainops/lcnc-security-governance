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

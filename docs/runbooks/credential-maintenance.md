# Local Vault credential maintenance

## Commands

Read-only report:

    .venv/bin/python scripts/maintain-vault-credentials.py

Rotate credentials approaching expiry or their use limit:

    .venv/bin/python scripts/maintain-vault-credentials.py --rotate-due

Explicitly rotate one selected role:

    .venv/bin/python scripts/maintain-vault-credentials.py --role governance-api --rotate

Rotation briefly stops the selected workloads. Governance API rotation
stops both replicas, temporarily interrupting inventory access.
The command checks mounted credentials and revokes diagnostic tokens.
Application functionality must be checked separately.

## macOS installation

From the repository root:

    .venv/bin/python scripts/install-credential-maintenance-launchagent.py
    plutil -lint "$HOME/Library/LaunchAgents/com.lcnc.credential-maintenance.plist"

Check whether the agent is already loaded:

    launchctl print "gui/$(id -u)/com.lcnc.credential-maintenance"

Only if it is not loaded:

    launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.lcnc.credential-maintenance.plist"

Do not repeat bootstrap for an already-loaded agent. Do not use sudo.

## Operation

The agent runs at load and approximately every five minutes.
Credentials are due when expiry is within two hours or remaining uses
are between one and ten. Zero uses denotes unlimited uses.
Locked roles and unavailable metadata require operator attention.

This local development implementation relies on the administrative
credential already configured inside the Vault container. No credential
values are stored in the LaunchAgent configuration.

Inspect:

    launchctl print "gui/$(id -u)/com.lcnc.credential-maintenance"
    tail -n 35 "$HOME/Library/Logs/LCNC/credential-maintenance.log"
    tail -n 10 "$HOME/Library/Logs/LCNC/credential-maintenance-error.log"

Exit code zero means the run completed without reported attention items.
A nonzero result requires reviewing the report and affected workloads.
Do not assume an empty error log means success; inspect standard output too.

Disable scheduled maintenance:

    launchctl bootout "gui/$(id -u)/com.lcnc.credential-maintenance"

To enable it again, use bootstrap.

## Limitations

- Requires a logged-in user, an awake Mac, and Docker.
- Credentials may expire while the Mac is asleep or offline.
- Expired/missing credentials and lockouts need operator recovery.
- Rotation failures can leave workloads stopped; inspect before retrying.
- Previous Secret IDs are retained until expiry or use exhaustion.
- No automatic lockout recovery, external alerts, or log rotation.
- Successful authentication does not establish full application functionality.
- Repeated failed scheduled runs require operator intervention.

## Verification — 2026-10-21 UTC

- Existing reporting and rotation/helper suites: 16 tests passed.
- Threshold-selection suite: nine tests passed.
- Live rotate-due run skipped all four roles outside the thresholds.
- LaunchAgent configuration passed plutil validation.
- Background runs observed at 05:04:13 and 05:09:14 UTC.
- Run count increased to two; latest exit code was zero.
- First background report checked all roles successfully.
- Automatic rotation at a real threshold remains unverified.
- Terminal-closure, login startup, and sleep/wake recovery remain unverified.

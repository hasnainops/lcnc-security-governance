# macOS platform status collector

The user LaunchAgent runs the collector independently of an open terminal.
It requires a logged-in user, an awake Mac and an available Docker engine.
Docker unavailability must remain visible as unavailable observations.

## Install configuration

From the repository root:

    .venv/bin/python scripts/install-platform-status-launchagent.py
    plutil -lint "$HOME/Library/LaunchAgents/com.lcnc.platform-status.plist"

The installer accepts an identical existing configuration and refuses to
overwrite a differing one. It does not load or restart the agent.

## Load once

Check for an already-loaded agent:

    launchctl print "gui/$(id -u)/com.lcnc.platform-status"

Check for a manually running collector:

    pgrep -fl '[c]ollect-platform-status.py'

Stop any manual collector with Ctrl-C in its own terminal before loading
the agent. Do not run two collectors.

If the agent is not already loaded:

    launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.lcnc.platform-status.plist"

Do not repeat bootstrap for an already-loaded agent or use sudo.

## Verify

    launchctl print "gui/$(id -u)/com.lcnc.platform-status"
    tail -n 5 "$HOME/Library/Logs/LCNC/platform-status.log"
    tail -n 10 "$HOME/Library/Logs/LCNC/platform-status-error.log"

Close the terminal, keep the Mac awake, and confirm that the portal's
observation timestamp continues advancing. Collection runs every 10 seconds.

## Stop and restart

Stop:

    launchctl bootout "gui/$(id -u)/com.lcnc.platform-status"

The snapshot becomes stale after collection stops.
To start again, use the bootstrap command above.

## Uninstall

Stop the agent first, then remove its configuration:

    rm "$HOME/Library/LaunchAgents/com.lcnc.platform-status.plist"

Logs are retained under ~/Library/Logs/LCNC.
Logs currently have no automatic rotation; monitor their size.
If the repository is moved or its virtual environment removed, update the
configuration before loading it again.

## Verification recorded on 2026-10-20

- Configuration passed plutil validation.
- Agent reported running with PID 23275.
- Repeated successful collections included all 20 services.
- Collection timestamps advanced approximately every 10 seconds.
- Error-log output was empty.
- Login startup and crash recovery remain untested.
- Terminal-closure verification requires explicit confirmation.
- Credential lifecycle and intermittent snapshot_missing remain open.

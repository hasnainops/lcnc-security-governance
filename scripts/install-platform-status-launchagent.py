#!/usr/bin/env python3
"""Create the macOS collector LaunchAgent configuration without loading it."""
import os
import plistlib
import shutil
import sys
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("This installer requires macOS.")

project = Path(__file__).resolve().parents[1]
python = project / ".venv/bin/python"
collector = project / "scripts/collect-platform-status.py"
docker = shutil.which("docker")
label = "com.lcnc.platform-status"
agent = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
logs = Path.home() / "Library/Logs/LCNC"

if not python.is_file() or not os.access(python, os.X_OK):
    raise SystemExit("Create the project's .venv first.")
if not collector.is_file() or not docker:
    raise SystemExit("Collector script or Docker executable is missing.")

config = {
    "Label": label,
    "ProgramArguments": [str(python), "-u", str(collector)],
    "WorkingDirectory": str(project),
    "EnvironmentVariables": {
        "HOME": str(Path.home()),
        "PATH": ":".join(dict.fromkeys([
            str(Path(docker).parent),
            "/usr/local/bin", "/opt/homebrew/bin",
            "/usr/bin", "/bin", "/usr/sbin", "/sbin",
        ])),
    },
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 10,
    "StandardOutPath": str(logs / "platform-status.log"),
    "StandardErrorPath": str(logs / "platform-status-error.log"),
}

if agent.exists():
    with agent.open("rb") as stream:
        existing = plistlib.load(stream)
    if existing != config:
        raise SystemExit("Existing configuration differs; review before replacing.")
    print("Matching LaunchAgent already installed; no changes made.")
else:
    agent.parent.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    with agent.open("xb") as stream:
        plistlib.dump(config, stream)
    agent.chmod(0o644)
    print(f"Created: {agent}")
    print("Configuration only; follow the runbook to load it.")

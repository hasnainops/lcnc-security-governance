"""Install configuration only; does not load or restart the LaunchAgent."""
import os
import plistlib
import shutil
import sys
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("This installer requires macOS.")

project = Path(__file__).resolve().parents[1]
label = "com.lcnc.credential-maintenance"
agent = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
logs = Path.home() / "Library/Logs/LCNC"
python = project / ".venv/bin/python"
script = project / "scripts/maintain-vault-credentials.py"
docker = shutil.which("docker")

if not python.is_file() or not os.access(python, os.X_OK):
    raise SystemExit("Project virtual environment Python is missing.")
if not script.is_file() or not docker:
    raise SystemExit("Maintenance script or Docker executable is missing.")

config = {
    "Label": label,
    "ProgramArguments": [str(python), "-u", str(script), "--rotate-due"],
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
    "StartInterval": 300,
    "StandardOutPath": str(logs / "credential-maintenance.log"),
    "StandardErrorPath": str(logs / "credential-maintenance-error.log"),
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
    print("Created:", agent)
    print("Configuration only; follow the runbook to load it.")

#!/usr/bin/env python3
"""Observe this Compose project. Run with --once or leave running; Ctrl-C stops."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "platform_status_contract", ROOT / "governance-api/app/platform_status.py"
)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)

COMPOSE = ["docker", "compose", "--project-directory", str(ROOT), "-f", str(ROOT / "docker-compose.yml")]
OUTPUT = ROOT / ".runtime-observability/platform-status.json"
TIMEOUT_SECONDS = 5
INTERVAL_SECONDS = 10
CONTAINER_ID = re.compile(r"[0-9a-f]{12,64}")
INSPECT_FORMAT = (
    '{"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"oneoff":{{json (index .Config.Labels "com.docker.compose.oneoff")}},'
    '"state":{{json .State.Status}},'
    '"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}},'
    '"image_id":{{json .Image}}}'
)


def command(args):
    # stderr can contain local configuration details; never forward it.
    completed = subprocess.run(args, cwd=ROOT, check=True, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, timeout=TIMEOUT_SECONDS)
    if len(completed.stdout) > 1024 * 1024:
        raise ValueError("Oversized Docker output")
    return completed.stdout


def collect(run=command):
    # Timestamp the start, so time spent collecting cannot make old data look newer.
    observed_at = contract.utc_now().isoformat()
    try:
        catalog = run(COMPOSE + ["config", "--services"]).split()
        if set(catalog) != set(contract.SERVICES) or len(catalog) != len(contract.SERVICES):
            return contract.collection_failure("catalog_mismatch", observed_at)
        ids = run(COMPOSE + ["ps", "--all", "--quiet", "--orphans=false"]).split()
        if len(ids) > 200 or len(ids) != len(set(ids)) or any(not CONTAINER_ID.fullmatch(i) for i in ids):
            raise ValueError("Invalid container IDs")
        records = []
        if ids:
            output = run(["docker", "inspect", "--type=container", "--format", INSPECT_FORMAT, *ids])
            records = [json.loads(line) for line in output.splitlines() if line.strip()]
            if len(records) != len(ids):
                raise ValueError("Incomplete inspection")
        return contract.build_snapshot(records, observed_at)
    except subprocess.TimeoutExpired:
        return contract.collection_failure("docker_timeout", observed_at)
    except (OSError, subprocess.CalledProcessError):
        return contract.collection_failure("docker_unavailable", observed_at)
    except (ValueError, TypeError, KeyError, RecursionError):
        return contract.collection_failure("invalid_docker_output", observed_at)


def write_snapshot(snapshot, path=OUTPUT):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The file contains only public status fields. API containers run as UID 10001.
    path.parent.chmod(0o755)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".status-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(snapshot, stream, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Write one snapshot and exit; nonzero if collection failed")
    args = parser.parse_args()
    try:
        while True:
            started = time.monotonic()
            snapshot = collect()
            try:
                write_snapshot(snapshot)
            except OSError:
                print("Unable to write the status snapshot; check directory permissions.", flush=True)
                return 1
            print(f'{snapshot["observed_at"]} collection={snapshot["collection_status"]} '
                  f'reason={snapshot["reason"] or "none"} services={len(snapshot["services"])}', flush=True)
            if args.once:
                return int(snapshot["collection_status"] != "ok")
            time.sleep(max(0, INTERVAL_SECONDS - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("Collector stopped; the last snapshot will become stale after 30 seconds.", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

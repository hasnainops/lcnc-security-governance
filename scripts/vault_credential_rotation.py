"""Explicit local credential rotation; never automatically unlock roles."""

import fcntl
import json
import os
import subprocess

SERVICES = {
    "governance-api": ("governance-api-a", "governance-api-b"),
    "enterprise-discovery": ("enterprise-discovery",),
    "governance-automation": ("governance-automation",),
    "appsmith-discovery": ("discovery",),
}

PROBE = '''
import json, os
from pathlib import Path
from urllib.request import Request, urlopen

expected = json.loads(input())
role = os.environ["VAULT_ROLE_ID"]
secret = Path(os.environ["VAULT_SECRET_ID_FILE"]).read_text().strip()
if role != expected["role"] or secret != expected["secret"]:
    raise SystemExit(1)

base = os.environ["VAULT_ADDR"].rstrip("/")
request = Request(
    base + "/v1/auth/approle/login",
    data=json.dumps({"role_id": role, "secret_id": secret}).encode(),
    headers={"Content-Type": "application/json"},
)
with urlopen(request, timeout=10) as response:
    token = json.load(response)["auth"]["client_token"]

request = Request(
    base + "/v1/auth/token/revoke-self",
    data=b"{}",
    headers={"X-Vault-Token": token, "Content-Type": "application/json"},
)
with urlopen(request, timeout=10):
    pass
'''


def compose(root, *args, payload=None):
    command = ["docker", "compose", *args]
    if args[0] == "start":
        container_ids = []
        for service in args[1:]:
            lookup = subprocess.run(
                ["docker", "compose", "ps", "--all", "--quiet", service],
                cwd=root, capture_output=True, text=True, timeout=20,
            )
            ids = lookup.stdout.split()
            if lookup.returncode or len(ids) != 1:
                raise RuntimeError(
                    f"Restart lookup failed for {service}; expected one container"
                )
            container_ids.append(ids[0])
        command = ["docker", "start", *container_ids]

    result = subprocess.run(
        command,
        cwd=root,
        input=payload,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode:
        raise RuntimeError(
            f"Container operation {args[0]} failed with exit code "
            f"{result.returncode}; raw output withheld"
        )


def rotate(root, role, vault, contains):
    services = SERVICES[role]
    path = root / ".runtime-secrets" / f"{role}-secret-id"

    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Expected regular credential file is missing")

    # Prevent overlapping rotations through this maintenance command.
    lock_path = root / ".runtime-secrets" / ".maintenance.lock"
    with lock_path.open("a") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        role_id = vault(
            "read", "-format=json",
            f"auth/approle/role/{role}/role-id",
        )["role_id"]
        locked = vault("read", "-format=json", "sys/locked-users")
        if contains(locked, role_id):
            raise RuntimeError("Role is locked; rotation refused")

        old_secret = path.read_text().strip()
        if not old_secret:
            raise RuntimeError("Existing credential is empty")

        # Fail closed if current credential metadata cannot be read.
        vault(
            "write", "-format=json",
            f"auth/approle/role/{role}/secret-id/lookup", "-",
            payload={"secret_id": old_secret},
        )

        # Refuse to change the running/stopped state of an idle workload.
        result = subprocess.run(
            ["docker", "compose", "ps", "--status", "running", "--services"],
            cwd=root, capture_output=True, text=True, timeout=20,
        )
        if result.returncode or not set(services).issubset(
            set(result.stdout.splitlines())
        ):
            raise RuntimeError("All selected workloads must already be running")

        stopped = False
        try:
            print("Stopping selected workloads:", ", ".join(services), flush=True)
            stopped = True
            compose(root, "stop", *services)

            issued = vault(
                "write", "-format=json", "-f",
                f"auth/approle/role/{role}/secret-id",
            )
            secret = issued["secret_id"]
            if not isinstance(secret, str) or not secret or any(
                character.isspace() for character in secret
            ):
                raise RuntimeError("Invalid issuance response")

            # In-place update preserves individual-file bind mounts.
            try:
                with path.open("r+") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.seek(0)
                    stream.write(secret + "\n")
                    stream.truncate()
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception:
                print("ERROR: Credential write failed; workloads remain stopped.")
                stopped = False
                raise

            print("Credential saved; no secrets printed.", flush=True)
        finally:
            if stopped:
                compose(root, "start", *services)

        for service in services:
            compose(
                root, "exec", "-T", service, "python", "-c", PROBE,
                payload=json.dumps({"role": role_id, "secret": secret}) + "\n",
            )
            print(f"PASS: {service} mounted credential accepted; diagnostic token revoked")

        print("Rotation verified. Previous Secret ID was not revoked.")
        print("Application functionality must be checked separately.")

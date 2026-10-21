"""Report credentials by default; rotate one role only with --rotate."""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLES = (
    "governance-api",
    "enterprise-discovery",
    "governance-automation",
    "appsmith-discovery",
)


def vault(*args, payload=None):
    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "vault",
            "sh", "-c",
            'export VAULT_ADDR=http://127.0.0.1:8200; '
            'export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"; '
            'exec vault "$@"',
            "vault-command", *args,
        ],
        cwd=ROOT,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode:
        raise RuntimeError("Vault operation failed")
    return json.loads(result.stdout)["data"]


def contains(value, target):
    if isinstance(value, dict):
        return any(contains(item, target) for item in value.values())
    if isinstance(value, list):
        return any(contains(item, target) for item in value)
    return value == target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=ROLES, action="append")
    parser.add_argument(
        "--rotate", action="store_true",
        help="Explicitly rotate one selected role; briefly stops its workloads",
    )
    args = parser.parse_args()
    if args.rotate:
        if not args.role or len(args.role) != 1:
            parser.error("--rotate requires exactly one --role")
        from vault_credential_rotation import rotate
        try:
            rotate(ROOT, args.role[0], vault, contains)
        except Exception:
            print("Rotation failed or verification incomplete; details withheld.")
            print("Check selected workload status before retrying.")
            return 1
        return 0
    roles = tuple(dict.fromkeys(args.role or ROLES))
    now = datetime.now(timezone.utc)
    print("Checked at:", now.isoformat())
    print("Mode: read-only; thresholds: 2 hours or 10 remaining uses")

    try:
        locked = vault("read", "-format=json", "sys/locked-users")
    except Exception:
        locked = None

    attention = False
    for role in roles:
        print(f"\n{role}")
        try:
            role_id = vault(
                "read", "-format=json",
                f"auth/approle/role/{role}/role-id",
            )["role_id"]
            is_locked = None if locked is None else contains(locked, role_id)
            print("  Locked:", "unknown" if is_locked is None else is_locked)

            secret = (ROOT / ".runtime-secrets" / f"{role}-secret-id").read_text().strip()
            if not secret:
                raise ValueError("Empty credential")

            data = vault(
                "write", "-format=json",
                f"auth/approle/role/{role}/secret-id/lookup", "-",
                payload={"secret_id": secret},
            )
            ttl = int(data["secret_id_ttl"])
            uses = int(data["secret_id_num_uses"])
            if ttl < 0 or uses < 0:
                raise ValueError("Invalid metadata")

            near_expiry = False
            if ttl == 0:
                print("  Expiry: no TTL limit")
            else:
                expiry = datetime.fromisoformat(
                    data["expiration_time"].replace("Z", "+00:00")
                )
                hours = (expiry - now).total_seconds() / 3600
                near_expiry = hours <= 2
                print("  Expires:", expiry.isoformat())
                print(f"  Hours remaining: {hours:.2f}")

            print("  Uses remaining:", "unlimited" if uses == 0 else uses)
            due = near_expiry or 0 < uses <= 10
            print("  Rotation:", "due" if due else "not due")

            if is_locked is True:
                print("  Recovery: operator review required")
            attention |= due or is_locked is not False

        except Exception:
            attention = True
            print("  Status: UNKNOWN; diagnostic details withheld")
            print("  No changes made")

    print("\nResult:", "attention required" if attention else "all checked credentials within thresholds")
    return 1 if attention else 0


if __name__ == "__main__":
    raise SystemExit(main())

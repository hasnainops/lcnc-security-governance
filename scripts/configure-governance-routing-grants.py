#!/usr/bin/env python3
"""Add only review-lock execution and discovery timestamp reads to the Vault role."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ROLE_PATH = "database/roles/governance-automation"
GRANTS = (
    'GRANT lcnc_governance_review_access TO "{{name}}" WITH INHERIT TRUE, SET FALSE;',
)


def vault(*args, payload=None):
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "vault", "sh", "-eu", "-c",
         'export VAULT_ADDR=http://127.0.0.1:8200; '
         'export VAULT_TOKEN="${VAULT_DEV_ROOT_TOKEN_ID:?}"; exec vault "$@"',
         "vault-command", *args], cwd=ROOT,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Vault operation failed; raw response withheld")
    return json.loads(result.stdout) if "-format=json" in args else None


def updated_role(data):
    allowed = {"db_name", "creation_statements", "revocation_statements", "rollback_statements",
               "renew_statements", "default_ttl", "max_ttl", "credential_type", "credential_config"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise RuntimeError("Unrecognized role fields; refusing to discard existing configuration")
    statements = data.get("creation_statements")
    if not isinstance(statements, list) or not statements or any(not isinstance(s, str) for s in statements):
        raise RuntimeError("Unexpected role creation statements")
    payload = dict(data)
    payload["creation_statements"] = list(statements)
    combined = " ".join(statements)
    for grant in GRANTS:
        if grant not in combined:
            payload["creation_statements"].append(grant)
    return payload


def main():
    # Check before changing Vault: issuing credentials must never reference a
    # missing function. Run against PostgreSQL using its existing local admin.
    check = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "sh", "-eu", "-c",
         'exec psql -X -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
        input="SELECT to_regprocedure('public.lock_application_for_review(uuid)') IS NOT NULL "
              "AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='lcnc_governance_review_access' "
              "AND NOT (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls));\n",
    )
    if check.returncode or check.stdout.strip() != "t":
        raise RuntimeError("Apply migration 025 before configuring routing grants")
    original = vault("read", "-format=json", ROLE_PATH)["data"]
    payload = updated_role(original)
    if payload != original:
        git_dir = Path(subprocess.check_output(
            ["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True,
        ).strip())
        backup_dir = Path(tempfile.mkdtemp(prefix="cr002-routing-grants-", dir=git_dir))
        backup_path = backup_dir / "governance-automation-role-before.json"
        descriptor = os.open(backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(original, handle, indent=2)
            handle.write("\n")
        print("Vault database role configuration backup:", backup_path)
        vault("write", ROLE_PATH, "-", payload=payload)
    saved = vault("read", "-format=json", ROLE_PATH)["data"]
    if saved != payload:
        raise RuntimeError("Role verification failed; existing clients have not been restarted")
    print("PASS: governance-automation routing grants configured; existing settings preserved.")
    print("AppRole credentials and limits were unchanged. Restart only governance-automation to obtain the new database grants.")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print("STOP:", str(exc))
        raise SystemExit(1)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("STOP: routing grant configuration incomplete (" + type(exc).__name__ + ").")
        raise SystemExit(1)

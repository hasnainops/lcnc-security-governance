#!/usr/bin/env python3
"""Add the LO1 table grants to the existing Vault DB role, preserving LO2 grants."""
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
GRANTS = (
    'GRANT SELECT ON TABLE public.application_owner_credentials TO "{{name}}";',
    'GRANT SELECT, INSERT ON TABLE public.application_owner_contexts TO "{{name}}";',
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
        raise RuntimeError("Vault operation failed")
    return json.loads(result.stdout) if "-format=json" in args else None


def updated_role(data):
    allowed = {"db_name", "creation_statements", "revocation_statements", "rollback_statements",
               "renew_statements", "default_ttl", "max_ttl", "credential_type", "credential_config"}
    if set(data) - allowed:
        raise RuntimeError("Unrecognized role fields; refusing to discard existing configuration")
    payload = {key: value for key, value in data.items() if key in allowed}
    statements = payload.get("creation_statements")
    if not isinstance(statements, list) or not statements or any(not isinstance(s, str) for s in statements):
        raise RuntimeError("Unexpected role creation statements")
    statements = list(statements)
    combined = " ".join(statements)
    for grant in GRANTS:
        if grant not in combined:
            statements.append(grant)
    payload["creation_statements"] = statements
    return payload


def main():
    original = vault("read", "-format=json", "database/roles/governance-api")["data"]
    payload = updated_role(original)
    if payload["creation_statements"] != original["creation_statements"]:
        vault("write", "database/roles/governance-api", "-", payload=payload)
    saved = vault("read", "-format=json", "database/roles/governance-api")["data"]
    if saved["creation_statements"] != payload["creation_statements"]:
        raise RuntimeError("Role verification failed")
    if any(saved.get(key) != value for key, value in original.items() if key != "creation_statements"):
        raise RuntimeError("Role settings changed unexpectedly; inspect before starting clients")
    print("PASS: existing Governance API grants preserved; LO1 grants configured.")
    print("Recreated API processes will obtain credentials with the added grants.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print("STOP: Vault grant update incomplete (" + type(exc).__name__ + ").")
        raise SystemExit(1)

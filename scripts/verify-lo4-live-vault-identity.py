"""LO4: temporary identity-backed authentication acceptance.

Development Vault only. Does not print credentials.
Creates isolated userpass identities and removes them afterward.
"""

import importlib.util
import json
import os
import secrets
import socket
import subprocess
import uuid
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]

CASES = (
    ("viewer", "lcnc-access-viewer", "viewer"),
    ("developer", "lcnc-access-developer", "developer"),
    ("reviewer", "lcnc-security-reviewer", "security_admin"),
    (
        "senior",
        "lcnc-senior-security-reviewer",
        "security_admin",
    ),
    ("unprivileged", "default", None),
)


def docker_vault(*arguments):
    command = [
        "docker", "compose", "exec", "-T", "vault",
        "sh", "-lc",
        (
            "set -eu; "
            "export VAULT_ADDR=http://127.0.0.1:8200; "
            'export VAULT_TOKEN="$VAULT_DEV_ROOT_TOKEN_ID"; '
            'vault "$@"'
        ),
        "lo4-test",
        *arguments,
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Development Vault command failed; "
            "raw output withheld."
        )

    return result.stdout.strip()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_denial(function, *args, status=403, **kwargs):
    try:
        function(*args, **kwargs)
    except Exception as exc:
        if getattr(exc, "status", None) == status:
            return
        raise AssertionError(
            f"Expected denial {status}; received different error"
        ) from None

    raise AssertionError(
        f"Expected HTTP {status} authentication denial"
    )


def main():
    # Validate host access before creating any accounts.
    port_result = subprocess.run(
        ["docker", "compose", "port", "vault", "8200"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if port_result.returncode != 0 or not port_result.stdout.strip():
        raise RuntimeError(
            "Vault port 8200 is not published to the host. "
            "No temporary identities created."
        )

    endpoint = port_result.stdout.strip().splitlines()[0]
    port = int(endpoint.rsplit(":", 1)[1])

    with socket.create_connection(
        ("127.0.0.1", port), timeout=5
    ):
        pass

    address = f"http://127.0.0.1:{port}"
    os.environ["VAULT_ADDR"] = address

    docker_vault("status")

    api = load_module(
        "lo4_live_api_identity",
        "governance-api/app/access_identity.py",
    )
    automation = load_module(
        "lo4_live_automation_identity",
        "governance-automation/app/reviewer_identity.py",
    )

    created_users = []
    issued_tokens = []
    created_entities = []

    cleanup_errors = []

    try:
        users = json.loads(
            docker_vault(
                "list", "-format=json", "auth/userpass/users"
            )
        )

        assert isinstance(users, list)

        print("Vault reachable; temporary test identities enabled.")
        print("Existing userpass accounts will not be modified.")

        for label, policy, expected_role in CASES:
            username = "lo4-accept-" + uuid.uuid4().hex
            password = secrets.token_urlsafe(32)

            assert username not in users

            # Register for cleanup before attempting creation.
            created_users.append(username)

            docker_vault(
                "write",
                f"auth/userpass/users/{username}",
                f"password={password}",
                f"policies={policy}",
                "token_ttl=5m",
                "token_max_ttl=5m",
            )

            login = json.loads(
                docker_vault(
                    "write", "-format=json",
                    f"auth/userpass/login/{username}",
                    f"password={password}",
                )
            )

            authentication = login["auth"]
            token = authentication["client_token"]

            assert isinstance(token, str) and token

            issued_tokens.append(token)

            entity = str(
                uuid.UUID(authentication["entity_id"])
            )
            created_entities.append(entity)

            header = "Bearer " + token

            if expected_role is None:
                expected_denial(
                    api.verified_access_principal,
                    header,
                )
                expected_denial(
                    automation.verified_access_principal,
                    header,
                )
                print("PASS: Unprivileged identity denied")
                continue

            expected = {
                "subject_id": "vault:" + entity,
                "role": expected_role,
            }

            assert (
                api.verified_access_principal(header)
                == expected
            )

            assert (
                automation.verified_access_principal(header)
                == expected
            )

            if label in ("reviewer", "senior"):
                reviewer_role = (
                    "Security/GRC Reviewer"
                    if label == "reviewer"
                    else "Senior Security/GRC Reviewer"
                )

                actor = automation.verified_reviewer(
                    header,
                    required_role=reviewer_role,
                )

                assert actor == expected["subject_id"]

            if label == "reviewer":
                expected_denial(
                    automation.verified_reviewer,
                    header,
                    required_role=(
                        "Senior Security/GRC Reviewer"
                    ),
                )

            print(
                f"PASS: {label} identity and "
                f"{expected_role} role verified"
            )

        expected_denial(
            api.verified_access_principal,
            None,
            status=401,
        )
        print("PASS: Missing bearer credential rejected")

        print()
        print("PASS: Live Vault-backed identity checks completed.")

    finally:
        # First revoke issued credentials.
        for token in reversed(issued_tokens):
            try:
                request = Request(
                    address + "/v1/auth/token/revoke-self",
                    data=b"{}",
                    headers={
                        "X-Vault-Token": token,
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )

                with urlopen(request, timeout=5):
                    pass

            except Exception:
                try:
                    docker_vault("token", "revoke", token)
                except Exception:
                    cleanup_errors.append(
                        "temporary token revocation"
                    )

        # Delete only uniquely generated test accounts.
        for username in reversed(created_users):
            try:
                docker_vault(
                    "delete",
                    f"auth/userpass/users/{username}",
                )
            except Exception:
                cleanup_errors.append(
                    "temporary userpass account deletion"
                )

        # Delete only entity IDs returned from test logins.
        for entity in reversed(list(dict.fromkeys(created_entities))):
            try:
                docker_vault(
                    "delete",
                    f"identity/entity/id/{entity}",
                )
            except Exception:
                cleanup_errors.append(
                    "temporary identity deletion"
                )

        # Check that no generated account or entity remains.
        try:
            remaining_users = json.loads(
                docker_vault(
                    "list", "-format=json",
                    "auth/userpass/users",
                )
            )

            remaining_entities = json.loads(
                docker_vault(
                    "list", "-format=json",
                    "identity/entity/id",
                )
            )

            if any(
                username in remaining_users
                for username in created_users
            ):
                cleanup_errors.append(
                    "temporary account still present"
                )

            if any(
                entity in remaining_entities
                for entity in created_entities
            ):
                cleanup_errors.append(
                    "temporary entity still present"
                )

        except Exception:
            cleanup_errors.append(
                "cleanup verification could not complete"
            )

        if cleanup_errors:
            print(
                "WARNING: Temporary Vault cleanup "
                "requires investigation."
            )
            print("Issues:", sorted(set(cleanup_errors)))
            raise RuntimeError(
                "Live identity acceptance cleanup incomplete."
            )

        print(
            "PASS: Temporary test credentials revoked."
        )
        print(
            "PASS: Temporary userpass accounts and "
            "identity entities removed."
        )
        print(
            "PASS: Existing Vault accounts preserved."
        )


if __name__ == "__main__":
    main()

"""Live LO4 authorization-boundary verification.

Uses temporary development-Vault accounts.
Does not intentionally create application or privilege records.
"""

import json
import runpy
import secrets
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]

helpers = runpy.run_path(
    str(ROOT / "scripts/verify-lo4-live-vault-identity.py")
)
vault = helpers["docker_vault"]

created_users = []
created_entities = []
issued_tokens = []

HTTP_PROBE = r'''
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

data = json.load(sys.stdin)

body = data.get("body")
payload = (
    json.dumps(body).encode()
    if body is not None else None
)

headers = {}
if data.get("token"):
    headers["Authorization"] = "Bearer " + data["token"]

if payload is not None:
    headers["Content-Type"] = "application/json"

request = Request(
    data["url"],
    data=payload,
    headers=headers,
    method=data["method"],
)

try:
    with urlopen(request, timeout=8) as response:
        status = response.status
        content = response.read(65536)
except HTTPError as exc:
    status = exc.code
    content = exc.read(4096)

try:
    document = json.loads(content)
except (ValueError, TypeError):
    document = {}

print(json.dumps({
    "status": status,
    "active": document.get("active"),
}))
'''


def probe(service, method, path, token=None, body=None):
    assert service in (
        "governance-api-a",
        "governance-api-b",
        "governance-automation",
    )

    port = 8007 if service == "governance-automation" else 8000

    request = {
        "method": method,
        "url": f"http://127.0.0.1:{port}{path}",
        "token": token,
        "body": body,
    }

    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T",
            service, "python", "-c", HTTP_PROBE,
        ],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=20,
        cwd=ROOT,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{service}: live HTTP probe failed to execute; "
            "raw diagnostic output withheld."
        )

    return json.loads(result.stdout)


def check(label, result, expected, active=None):
    assert result["status"] == expected, (
        f"{label}: expected HTTP {expected}, "
        f"received {result['status']}"
    )

    if active is not None:
        assert result["active"] is active, label

    print(f"PASS: {label} — HTTP {expected}")


def create_identity(role, policy):
    username = "lo4-accept-" + uuid.uuid4().hex
    password = secrets.token_urlsafe(32)

    # Record the name before creation, so partial creation
    # can still be cleaned up.
    created_users.append(username)

    vault(
        "write",
        f"auth/userpass/users/{username}",
        f"password={password}",
        f"policies={policy}",
        "token_ttl=5m",
        "token_max_ttl=5m",
    )

    login = json.loads(
        vault(
            "write", "-format=json",
            f"auth/userpass/login/{username}",
            f"password={password}",
        )
    )["auth"]

    token = login["client_token"]
    entity = str(uuid.UUID(login["entity_id"]))

    issued_tokens.append(token)
    created_entities.append(entity)

    print(f"PASS: Temporary {role} identity authenticated")

    return token, "vault:" + entity


def run_checks():
    baseline_users = json.loads(
        vault("list", "-format=json", "auth/userpass/users")
    )
    baseline_entities = json.loads(
        vault("list", "-format=json", "identity/entity/id")
    )

    assert isinstance(baseline_users, list)
    assert isinstance(baseline_entities, list)

    print("Initial Vault userpass accounts:", len(baseline_users))
    print("Initial Vault identities:", len(baseline_entities))

    viewer_token, viewer = create_identity(
        "viewer", "lcnc-access-viewer"
    )
    reviewer_token, reviewer = create_identity(
        "reviewer", "lcnc-security-reviewer"
    )

    app_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    grant_id = str(uuid.uuid4())

    automation = "governance-automation"

    check(
        "Viewer cannot list JIT requests",
        probe(
            automation, "GET", "/privileges/requests",
            viewer_token,
        ),
        403,
    )

    check(
        "Reviewer can list JIT requests",
        probe(
            automation, "GET", "/privileges/requests",
            reviewer_token,
        ),
        200,
    )

    check(
        "Viewer cannot list grants",
        probe(
            automation, "GET", "/privileges/grants",
            viewer_token,
        ),
        403,
    )

    check(
        "Viewer cannot trigger expiry",
        probe(
            automation, "POST", "/privileges/expire/run",
            viewer_token,
        ),
        403,
    )

    query = urlencode({
        "application_id": app_id,
        "subject_id": viewer,
        "action": "export",
    })

    check(
        "Verified viewer has no fixture grant",
        probe(
            automation, "GET",
            "/privileges/check?" + query,
            viewer_token,
        ),
        200,
        active=False,
    )

    spoofed_query = urlencode({
        "application_id": app_id,
        "subject_id": reviewer,
        "action": "export",
    })

    check(
        "Viewer cannot query another subject's grant",
        probe(
            automation, "GET",
            "/privileges/check?" + spoofed_query,
            viewer_token,
        ),
        403,
    )

    jit_request = {
        "application_id": app_id,
        "subject_id": viewer,
        "base_role": "viewer",
        "requested_action": "export",
        "justification": "LO4 isolated boundary check",
        "requested_duration_minutes": 15,
    }

    check(
        "Authenticated requester reaches application lookup",
        probe(
            automation, "POST", "/privileges/requests",
            viewer_token, jit_request,
        ),
        404,
    )

    spoofed_request = dict(jit_request)
    spoofed_request["base_role"] = "security_admin"

    check(
        "Requester role escalation rejected",
        probe(
            automation, "POST", "/privileges/requests",
            viewer_token, spoofed_request,
        ),
        403,
    )

    check(
        "Verified reviewer reaches decision lookup",
        probe(
            automation, "POST",
            f"/privileges/requests/{request_id}/decision",
            reviewer_token,
            {
                "decision": "reject",
                "actor": reviewer,
                "reason": "Isolated acceptance test",
            },
        ),
        404,
    )

    check(
        "Verified reviewer reaches revocation lookup",
        probe(
            automation, "POST",
            f"/privileges/grants/{grant_id}/revoke",
            reviewer_token,
            {
                "actor": reviewer,
                "reason": "Isolated acceptance test",
            },
        ),
        404,
    )

    for service in ("governance-api-a", "governance-api-b"):
        path = f"/applications/{app_id}/authorize"

        valid = {
            "subject_id": viewer,
            "role": "viewer",
            "action": "read",
        }

        check(
            f"{service}: authenticated application lookup",
            probe(
                service, "POST", path,
                viewer_token, valid,
            ),
            404,
        )

        changed_role = dict(valid)
        changed_role["role"] = "security_admin"

        check(
            f"{service}: role impersonation rejected",
            probe(
                service, "POST", path,
                viewer_token, changed_role,
            ),
            403,
        )

        changed_subject = dict(valid)
        changed_subject["subject_id"] = reviewer

        check(
            f"{service}: subject impersonation rejected",
            probe(
                service, "POST", path,
                viewer_token, changed_subject,
            ),
            403,
        )

    print()
    print("PASS: Live authentication and authorization boundaries verified.")
    print("NOTE: No application or privilege fixtures created.")


def cleanup():
    errors = []

    for token in reversed(issued_tokens):
        try:
            vault("token", "revoke", token)
        except Exception:
            errors.append("temporary token revocation")

    for username in reversed(created_users):
        try:
            vault("delete", f"auth/userpass/users/{username}")
        except Exception:
            errors.append("temporary user deletion")

    for entity in reversed(created_entities):
        try:
            vault("delete", f"identity/entity/id/{entity}")
        except Exception:
            errors.append("temporary entity deletion")

    try:
        users = json.loads(
            vault("list", "-format=json", "auth/userpass/users")
        )
        entities = json.loads(
            vault("list", "-format=json", "identity/entity/id")
        )

        if any(name in users for name in created_users):
            errors.append("test user remains")

        if any(entity in entities for entity in created_entities):
            errors.append("test identity remains")

        print("Remaining Vault userpass accounts:", len(users))
        print("Remaining Vault identities:", len(entities))

    except Exception:
        errors.append("cleanup inventory verification")

    if errors:
        raise RuntimeError(
            "Temporary Vault cleanup requires investigation: "
            + ", ".join(sorted(set(errors)))
        )

    print("PASS: Temporary tokens, accounts and identities cleaned.")


if __name__ == "__main__":
    try:
        run_checks()
    finally:
        cleanup()

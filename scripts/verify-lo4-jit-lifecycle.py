"""Live LO4.2 JIT lifecycle acceptance.

Creates one isolated application and two temporary Vault users.
Tests OPA DENY -> JIT ALLOW -> revocation DENY -> expiry DENY.
Deletes fixture-linked database records and temporary identities.
"""

import json
import runpy
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

helpers = runpy.run_path(
    str(ROOT / "scripts/verify-lo4-live-http-boundaries.py")
)

create_identity = helpers["create_identity"]
cleanup_identities = helpers["cleanup"]

APP_ID = str(uuid.uuid4())
EXTERNAL_ID = "lo4-jit-accept-" + uuid.uuid4().hex


HTTP_CODE = r'''
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

item = json.load(sys.stdin)

body = item.get("body")
payload = json.dumps(body).encode() if body is not None else None

headers = {}
if item.get("token"):
    headers["Authorization"] = "Bearer " + item["token"]
if payload is not None:
    headers["Content-Type"] = "application/json"

request = Request(
    item["url"],
    data=payload,
    headers=headers,
    method=item["method"],
)

try:
    with urlopen(request, timeout=10) as response:
        status = response.status
        content = response.read(131072)
except HTTPError as exc:
    status = exc.code
    content = exc.read(131072)

try:
    document = json.loads(content)
except (ValueError, TypeError):
    document = {}

print(json.dumps({
    "status": status,
    "body": document,
}))
'''


def db(operation, **kwargs):
    """Use API registration and narrowly scoped admin fixture maintenance."""
    global APP_ID

    if operation == "create":
        created = http(
            "governance-api-a",
            "POST",
            "/applications",
            body={
                "external_id": EXTERNAL_ID,
                "name": "LO4 Isolated JIT Acceptance Fixture",
                "platform": "isolated-acceptance",
                "registration_status": "registered",
                "lifecycle_status": "active",
                "data_classification": "internal",
                "internet_exposed": False,
            },
        )

        if created["status"] != 201:
            raise RuntimeError(
                "Governance API application registration failed "
                f"with HTTP {created['status']}."
            )

        record = created["body"]

        if record.get("external_id") != EXTERNAL_ID:
            raise RuntimeError(
                "Application registration returned an unexpected fixture."
            )

        APP_ID = str(uuid.UUID(str(record["id"])))
        return {"created": True}

    sql = {
        "backdate": """
            WITH changed AS (
                UPDATE privilege_grants AS pg
                SET expires_at = NOW() - INTERVAL '1 second'
                FROM applications AS a
                WHERE pg.id = :'grant_id'::uuid
                  AND pg.application_id = :'app_id'::uuid
                  AND a.id = pg.application_id
                  AND a.external_id = :'external_id'
                  AND a.platform = 'isolated-acceptance'
                  AND pg.status = 'active'
                RETURNING pg.id
            )
            SELECT json_build_object(
                'backdated', (SELECT COUNT(*) = 1 FROM changed)
            )::text;
        """,
        "expired_others": """
            SELECT json_build_object(
                'expired_others', (
                    SELECT COUNT(*)
                    FROM privilege_grants
                    WHERE status = 'active'
                      AND expires_at <= NOW()
                      AND application_id <> :'app_id'::uuid
                )
            )::text;
        """,
        "snapshot": """
            SELECT json_build_object(
                'grant_statuses', COALESCE((
                    SELECT json_agg(status ORDER BY granted_at)
                    FROM privilege_grants
                    WHERE application_id = :'app_id'::uuid
                ), '[]'::json),
                'events', COALESCE((
                    SELECT json_object_agg(event_type, event_count)
                    FROM (
                        SELECT
                            e.event_type,
                            COUNT(*) AS event_count
                        FROM privilege_events e
                        JOIN privilege_requests r
                          ON r.id = e.privilege_request_id
                        WHERE r.application_id = :'app_id'::uuid
                        GROUP BY e.event_type
                    ) AS totals
                ), '{}'::json),
                'access_decisions', (
                    SELECT COUNT(*)
                    FROM access_decisions
                    WHERE application_id = :'app_id'::uuid
                )
            )::text;
        """,
        "cleanup": """
            WITH deleted AS (
                DELETE FROM applications
                WHERE external_id = :'external_id'
                  AND name = 'LO4 Isolated JIT Acceptance Fixture'
                  AND platform = 'isolated-acceptance'
                RETURNING id
            )
            SELECT json_build_object(
                'fixture_deleted',
                EXISTS(SELECT 1 FROM deleted)
            )::text;
        """,
        "verify": """
            SELECT json_build_object(
                'applications', (
                    SELECT COUNT(*)
                    FROM applications
                    WHERE id = :'app_id'::uuid
                       OR external_id = :'external_id'
                ),
                'requests', (
                    SELECT COUNT(*)
                    FROM privilege_requests
                    WHERE application_id = :'app_id'::uuid
                ),
                'grants', (
                    SELECT COUNT(*)
                    FROM privilege_grants
                    WHERE application_id = :'app_id'::uuid
                ),
                'decisions', (
                    SELECT COUNT(*)
                    FROM access_decisions
                    WHERE application_id = :'app_id'::uuid
                ),
                'events', (
                    SELECT COUNT(*)
                    FROM privilege_events e
                    JOIN privilege_requests r
                      ON r.id = e.privilege_request_id
                    WHERE r.application_id = :'app_id'::uuid
                )
            )::text;
        """,
    }

    if operation not in sql:
        raise ValueError("Unsupported fixture operation")

    shell = (
        'set -eu; : "${POSTGRES_USER:?}"; '
        'DB="${POSTGRES_DB:-$POSTGRES_USER}"; '
        'exec psql -X -qAt -v ON_ERROR_STOP=1 '
        '-U "$POSTGRES_USER" -d "$DB" "$@"'
    )

    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T",
            "postgres", "sh", "-lc",
            shell,
            "lo4-acceptance-admin",
            "-v", f"app_id={APP_ID}",
            "-v", f"external_id={EXTERNAL_ID}",
            "-v", f"grant_id={kwargs.get('grant_id', uuid.UUID(int=0))}",
        ],
        cwd=ROOT,
        input=sql[operation],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode:
        raise RuntimeError(
            f"Scoped administrative fixture operation failed: {operation}. "
            "Raw diagnostic output withheld."
        )

    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if len(lines) != 1:
        raise RuntimeError(
            f"Unexpected administrative response: {operation}."
        )

    return json.loads(lines[0])



def http(service, method, path, token=None, body=None):
    if service not in (
        "governance-api-a",
        "governance-api-b",
        "governance-automation",
    ):
        raise ValueError("Unexpected service")

    port = 8007 if service == "governance-automation" else 8000

    payload = {
        "url": f"http://127.0.0.1:{port}{path}",
        "method": method,
        "token": token,
        "body": body,
    }

    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T",
            service, "python", "-c", HTTP_CODE,
        ],
        cwd=ROOT,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Live HTTP check failed: {service}. "
            "Raw output withheld."
        )

    return json.loads(result.stdout)


def expect_status(label, response, expected):
    actual = response["status"]
    assert actual == expected, (
        f"{label}: expected HTTP {expected}, received {actual}"
    )
    print(f"PASS: {label} — HTTP {expected}")
    return response["body"]


def authorize(service, token, subject, expected):
    response = http(
        service,
        "POST",
        f"/applications/{APP_ID}/authorize",
        token,
        {
            "subject_id": subject,
            "role": "viewer",
            "action": "export",
        },
    )

    body = expect_status(
        f"{service}: OPA {expected.upper()}",
        response,
        200,
    )

    assert body.get("allowed") is (expected == "allow"), (
        f"{service}: unexpected OPA permission"
    )

    assert body.get("decision") == expected, (
        f"{service}: unexpected decision action"
    )


def request_and_approve(
    viewer_token, viewer_subject,
    reviewer_token, reviewer_subject,
):
    request = expect_status(
        "Authenticated JIT request created",
        http(
            "governance-automation",
            "POST",
            "/privileges/requests",
            viewer_token,
            {
                "application_id": APP_ID,
                "subject_id": viewer_subject,
                "base_role": "viewer",
                "requested_action": "export",
                "justification": (
                    "Isolated LO4 lifecycle acceptance"
                ),
                "requested_duration_minutes": 5,
            },
        ),
        201,
    )

    request_id = str(uuid.UUID(request["id"]))

    approval = expect_status(
        "Verified reviewer approved JIT request",
        http(
            "governance-automation",
            "POST",
            f"/privileges/requests/{request_id}/decision",
            reviewer_token,
            {
                "decision": "approve",
                "actor": reviewer_subject,
                "reason": (
                    "Isolated LO4 lifecycle acceptance"
                ),
            },
        ),
        200,
    )

    grant = approval["grant"]
    grant_id = str(uuid.UUID(grant["id"]))

    assert grant["status"] == "active"

    return grant_id


def run_acceptance():
    print("===== ISOLATED APPLICATION FIXTURE =====")
    assert db("create")["created"]
    print("PASS: Unique registered application created")

    viewer_token, viewer = create_identity(
        "viewer", "lcnc-access-viewer"
    )

    reviewer_token, reviewer = create_identity(
        "reviewer", "lcnc-security-reviewer"
    )

    print()
    print("===== INITIAL OPA DENY =====")

    for service in ("governance-api-a", "governance-api-b"):
        authorize(service, viewer_token, viewer, "deny")

    print()
    print("===== JIT APPROVAL AND OPA ALLOW =====")

    first_grant = request_and_approve(
        viewer_token, viewer,
        reviewer_token, reviewer,
    )

    for service in ("governance-api-a", "governance-api-b"):
        authorize(service, viewer_token, viewer, "allow")

    print()
    print("===== REVOCATION =====")

    revoked = expect_status(
        "Reviewer revoked active grant",
        http(
            "governance-automation",
            "POST",
            f"/privileges/grants/{first_grant}/revoke",
            reviewer_token,
            {
                "actor": reviewer,
                "reason": (
                    "Isolated LO4 revocation acceptance"
                ),
            },
        ),
        200,
    )

    assert revoked["status"] == "revoked"

    for service in ("governance-api-a", "governance-api-b"):
        authorize(service, viewer_token, viewer, "deny")

    print()
    print("===== EXPIRY =====")

    second_grant = request_and_approve(
        viewer_token, viewer,
        reviewer_token, reviewer,
    )

    for service in ("governance-api-a", "governance-api-b"):
        authorize(service, viewer_token, viewer, "allow")

    assert db("expired_others")["expired_others"] == 0, (
        "Other overdue active grants exist; refusing shared expiry."
    )

    # Accelerate expiry on the isolated fixture only.
    assert db(
        "backdate",
        grant_id=second_grant,
    )["backdated"]

    print("PASS: Only isolated second grant backdated")

    assert db("expired_others")["expired_others"] == 0, (
        "Another overdue grant appeared; refusing shared expiry."
    )

    expect_status(
        "Authorized expiry maintenance executed",
        http(
            "governance-automation",
            "POST",
            "/privileges/expire/run",
            reviewer_token,
        ),
        200,
    )

    for service in ("governance-api-a", "governance-api-b"):
        authorize(service, viewer_token, viewer, "deny")

    print()
    print("===== PERSISTED AUDIT EVIDENCE =====")

    snapshot = db("snapshot")

    statuses = snapshot["grant_statuses"]
    events = snapshot["events"]

    assert sorted(statuses) == ["expired", "revoked"], (
        f"Unexpected grant lifecycle states: {statuses}"
    )

    required_events = {
        "privilege_requested": 2,
        "privilege_granted": 2,
        "privilege_revoked": 1,
        "privilege_expired": 1,
    }

    for event_type, minimum in required_events.items():
        assert events.get(event_type, 0) >= minimum, (
            f"Missing persisted audit event: {event_type}"
        )

    assert snapshot["access_decisions"] >= 8

    print("Grant states:", sorted(statuses))
    print("Audit event counts:", events)
    print(
        "Persisted OPA access decisions:",
        snapshot["access_decisions"],
    )

    print()
    print("PASS: Full deployed JIT lifecycle accepted.")


def cleanup():
    errors = []

    print()
    print("===== ISOLATED FIXTURE CLEANUP =====")

    try:
        deleted = db("cleanup")
        print(
            "Fixture application deleted:",
            deleted["fixture_deleted"],
        )

        remaining = db("verify")
        print("Remaining fixture-linked records:", remaining)

        if any(remaining.values()):
            errors.append("fixture records remain")

    except Exception:
        errors.append("fixture database cleanup failed")

    try:
        cleanup_identities()
    except Exception:
        errors.append("temporary Vault identity cleanup failed")

    if errors:
        raise RuntimeError(
            "Cleanup incomplete: " + ", ".join(errors)
        )

    print("PASS: Isolated database fixture cleaned")
    print("PASS: Temporary Vault identities cleaned")
    print("PASS: Existing application records untouched")


if __name__ == "__main__":
    try:
        run_acceptance()
    finally:
        cleanup()

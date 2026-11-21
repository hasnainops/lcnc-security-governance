"""LO4.1 live DLP audit acceptance using one disposable application."""

import json
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXTERNAL_ID = "lo4-dlp-audit-" + uuid.uuid4().hex
APPLICATION_NAME = "LO4 Isolated DLP Audit Fixture"
PLATFORM = "isolated-acceptance"
MARKER = "LO4_SYNTHETIC_" + uuid.uuid4().hex

APP_ID = None

POSTGRES_SHELL = (
    'set -eu; '
    ': "${POSTGRES_USER:?}"; '
    'DB="${POSTGRES_DB:-$POSTGRES_USER}"; '
    'exec psql -X -qAt -v ON_ERROR_STOP=1 '
    '-U "$POSTGRES_USER" -d "$DB" "$@"'
)

HTTP_PROBE = r'''
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

item = json.load(sys.stdin)

req = Request(
    item["url"],
    data=json.dumps(item["body"]).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urlopen(req, timeout=25) as response:
        status = response.status
        content = response.read(131072)
except HTTPError as error:
    status = error.code
    content = error.read(131072)

try:
    body = json.loads(content)
except (ValueError, TypeError):
    body = {}

print(json.dumps({"status": status, "body": body}))
'''


def database(query, application_id=None):
    identity = application_id or APP_ID or str(uuid.UUID(int=0))

    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T",
            "postgres",
            "sh", "-lc",
            POSTGRES_SHELL,
            "lo4-dlp-admin",
            "-v", f"external_id={EXTERNAL_ID}",
            "-v", f"app_id={identity}",
        ],
        cwd=ROOT,
        input=query,
        text=True,
        capture_output=True,
        timeout=30,
    )

    if result.returncode:
        raise RuntimeError(
            "Scoped PostgreSQL acceptance operation failed. "
            "Raw diagnostics withheld."
        )

    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    assert len(lines) == 1, (
        "Unexpected PostgreSQL response format"
    )

    return json.loads(lines[0])


def api(path, payload):
    result = subprocess.run(
        [
            "docker", "compose", "exec", "-T",
            "governance-api-a",
            "python", "-c", HTTP_PROBE,
        ],
        cwd=ROOT,
        input=json.dumps(
            {
                "url": f"http://127.0.0.1:8000{path}",
                "body": payload,
            }
        ),
        text=True,
        capture_output=True,
        timeout=40,
    )

    if result.returncode:
        raise RuntimeError(
            "Governance API acceptance request failed. "
            "Raw diagnostics withheld."
        )

    return json.loads(result.stdout)


BASELINE_QUERY = """
SELECT json_build_object(
    'transfer_events',
    (SELECT COUNT(*) FROM integration_transfer_events),
    'acceptance_fixtures',
    (
        SELECT COUNT(*)
        FROM applications
        WHERE external_id LIKE 'lo4-dlp-audit-%'
    )
)::text;
"""

AUDIT_QUERY = """
SELECT COALESCE(
    json_agg(row_to_json(receipt)),
    '[]'::json
)::text
FROM (
    SELECT
        id::text AS id,
        application_id::text AS application_id,
        destination_scheme,
        destination_host,
        destination_trust,
        declared_classification,
        effective_sensitivity,
        decision,
        allowed,
        reasons,
        dlp_sensitive_data_detected,
        dlp_finding_count,
        dlp_highest_sensitivity,
        dlp_detected_types,
        gateway_version,
        dlp_engine_version,
        enforcement_outcome
    FROM integration_transfer_events
    WHERE application_id = :'app_id'::uuid
    ORDER BY evaluated_at
) AS receipt;
"""

CLEANUP_QUERY = """
WITH deleted AS (
    DELETE FROM applications
    WHERE external_id = :'external_id'
      AND name = 'LO4 Isolated DLP Audit Fixture'
      AND platform = 'isolated-acceptance'
    RETURNING id
)
SELECT json_build_object(
    'deleted_applications',
    COUNT(*)
)::text
FROM deleted;
"""

VERIFY_CLEANUP_QUERY = """
SELECT json_build_object(
    'applications',
    (
        SELECT COUNT(*)
        FROM applications
        WHERE external_id = :'external_id'
    ),
    'transfer_events',
    (
        SELECT COUNT(*)
        FROM integration_transfer_events
        WHERE application_id = :'app_id'::uuid
    )
)::text;
"""


def run():
    global APP_ID

    print("===== BEFORE: READ-ONLY BASELINE =====")

    baseline = database(BASELINE_QUERY)

    print("Existing transfer events:", baseline["transfer_events"])
    print(
        "Existing acceptance fixtures:",
        baseline["acceptance_fixtures"],
    )

    assert baseline["acceptance_fixtures"] == 0, (
        "Previous acceptance fixture found; refusing new fixture"
    )

    try:
        print()
        print("===== CREATE ISOLATED APPLICATION =====")

        created = api(
            "/applications",
            {
                "external_id": EXTERNAL_ID,
                "name": APPLICATION_NAME,
                "platform": PLATFORM,
                "registration_status": "registered",
                "lifecycle_status": "active",
                "data_classification": "public",
                "internet_exposed": False,
            },
        )

        assert created["status"] == 201, (
            "Isolated application registration failed"
        )

        application = created["body"]

        assert application["external_id"] == EXTERNAL_ID
        assert application["data_classification"] == "public"

        APP_ID = str(uuid.UUID(str(application["id"])))

        print("PASS: Isolated application registered")
        print("PASS: Authoritative classification stored as public")

        print()
        print("===== REJECT CALLER-SUPPLIED TRUST CLAIMS =====")

        transfer = {
            "destination_url": (
                "https://1.1.1.1/lo4-dlp-audit-test"
            ),
            "content": MARKER,
            "field_names": ["ssn"],
        }

        forged = api(
            f"/applications/{APP_ID}/evaluate-transfer",
            {
                **transfer,
                "declared_classification": "public",
                "destination_trust": "internal",
            },
        )

        assert forged["status"] == 422, (
            "Caller-supplied classification or trust was accepted"
        )

        print(
            "PASS: Forged classification and trust fields "
            "rejected — HTTP 422"
        )

        print()
        print("===== LIVE GOVERNANCE API → GATEWAY → DLP =====")

        evaluation = api(
            f"/applications/{APP_ID}/evaluate-transfer",
            transfer,
        )

        assert evaluation["status"] == 200, (
            "Live transfer evaluation did not succeed"
        )

        body = evaluation["body"]

        assert body["declared_classification"] == "public"
        assert body["effective_sensitivity"] == "restricted"
        assert body["decision"] == "block"
        assert body["allowed"] is False

        assert body["dlp"]["sensitive_data_detected"] is True
        assert body["dlp"]["finding_count"] >= 1
        assert (
            body["dlp"]["highest_sensitivity"]
            == "restricted"
        )
        assert "restricted_field_schema" in (
            body["dlp"]["detected_types"]
        )

        assert MARKER not in json.dumps(body)

        event_id = str(uuid.UUID(str(body["event_id"])))

        print("PASS: Live DLP detected restricted schema data")
        print("PASS: Public declaration elevated to restricted")
        print("PASS: External transfer BLOCKED")
        print("PASS: Raw synthetic content absent from response")

        print()
        print("===== VERIFY PERSISTED POSTGRESQL EVIDENCE =====")

        records = database(AUDIT_QUERY)

        assert len(records) == 1, (
            "Expected exactly one scoped transfer audit event"
        )

        receipt = records[0]

        assert receipt["id"] == event_id
        assert receipt["application_id"] == APP_ID
        assert receipt["declared_classification"] == "public"
        assert receipt["effective_sensitivity"] == "restricted"
        assert receipt["decision"] == "block"
        assert receipt["allowed"] is False
        assert receipt["dlp_sensitive_data_detected"] is True
        assert receipt["dlp_finding_count"] >= 1
        assert receipt["dlp_highest_sensitivity"] == "restricted"

        assert "restricted_field_schema" in (
            receipt["dlp_detected_types"]
        )

        assert (
            "restricted_data_external_transfer"
            in receipt["reasons"]
        )

        assert receipt["destination_scheme"] == "https"
        assert receipt["destination_host"] == "1.1.1.1"

        assert MARKER not in json.dumps(receipt)

        # This endpoint evaluates and records the decision.
        # It does not execute controlled egress.
        assert receipt["enforcement_outcome"] is None

        print("PASS: Matching PostgreSQL audit event persisted")
        print("PASS: Authoritative classification retained")
        print("PASS: Detected restricted sensitivity recorded")
        print("PASS: BLOCK decision and reason recorded")
        print("PASS: Only metadata persisted; raw content absent")
        print(
            "PASS: Evaluation-only receipt correctly has "
            "no execution outcome"
        )

        print()
        print("PASS: LO4.1 live classification/DLP audit accepted")

    finally:
        print()
        print("===== GUARANTEED FIXTURE CLEANUP ATTEMPT =====")

        cleanup = database(CLEANUP_QUERY)

        assert cleanup["deleted_applications"] <= 1, (
            "Unexpected cleanup scope"
        )

        remaining = database(VERIFY_CLEANUP_QUERY)

        assert remaining == {
            "applications": 0,
            "transfer_events": 0,
        }, f"Fixture records remain: {remaining}"

        after = database(BASELINE_QUERY)

        assert (
            after["transfer_events"]
            == baseline["transfer_events"]
        ), (
            "Global audit count changed unexpectedly; "
            "check for concurrent database activity"
        )

        assert after["acceptance_fixtures"] == 0

        print(
            "Fixture applications deleted:",
            cleanup["deleted_applications"],
        )
        print("Remaining fixture records:", remaining)
        print(
            "Transfer audit baseline restored:",
            after["transfer_events"],
        )

        print("PASS: Isolated fixture and audit record cleaned")
        print("PASS: Existing transfer audit records preserved")


if __name__ == "__main__":
    run()

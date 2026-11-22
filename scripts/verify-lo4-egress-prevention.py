"""LO4.3 deployed BLOCK-to-enforcement-receipt acceptance.

Run inside a Governance API container.

Authentication/authorization are synthetic mocks.
Gateway, DLP Engine, transfer evaluation and PostgreSQL
persistence are real.

No external outbound HTTP execution is permitted.
"""

import json
import os
import re
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient

from app import integration, main
from app.database import get_connection


SUFFIX = os.environ.get("LO4_EGRESS_SUFFIX", "")

if (
    os.environ.get("LO4_EGRESS_SUPERVISED") != "1"
    or not re.fullmatch(r"[0-9a-f]{32}", SUFFIX)
):
    raise RuntimeError(
        "Run with scripts/run-lo4-egress-prevention.py"
    )

EXTERNAL_ID = f"lo4-egress-audit-{SUFFIX}"
APP_NAME = "LO4 Isolated Egress Prevention Fixture"
PLATFORM = "isolated-acceptance"

CONTENT = f"LO4_SYNTHETIC_EGRESS_{SUFFIX}"
TOKEN = "Bearer lo4-isolated-fixture"

SUBJECT = "vault:11111111-2222-3333-4444-555555555555"

APP_ID = None


def count(query, params=()):
    with get_connection() as connection:
        return connection.execute(
            query, params
        ).fetchone()["n"]


def verified_principal(authorization):
    assert authorization == TOKEN

    return {
        "subject_id": SUBJECT,
        "role": "developer",
    }


def authorized_export(application_id, request, authorization=None):
    assert application_id == APP_ID
    assert authorization == TOKEN
    assert request.subject_id == SUBJECT
    assert request.role == "developer"
    assert request.action == "export"

    return {
        "allowed": True,
        "decision": "allow",
    }


def scoped_export_grant(application_id, request, authorization=None):
    assert application_id == APP_ID
    assert authorization == TOKEN
    assert request.subject_id == SUBJECT
    assert request.action == "export"

    return {
        "active": True,
        "grant_id": "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb",
        "granted_action": "export",
    }


def accepted_governance(application_id):
    assert application_id == APP_ID

    return {"allowed": True}


def run():

    global APP_ID

    print("===== BASELINE =====")

    baseline = count(
        "SELECT COUNT(*) AS n FROM integration_transfer_events"
    )

    assert count(
        """
        SELECT COUNT(*) AS n
        FROM applications
        WHERE external_id = %s
        """,
        (EXTERNAL_ID,),
    ) == 0

    print("Original transfer audit records:", baseline)

    try:
        print()
        print("===== REGISTER ISOLATED APPLICATION =====")

        with TestClient(main.app) as client:

            registration = client.post(
                "/applications",
                json={
                    "external_id": EXTERNAL_ID,
                    "name": APP_NAME,
                    "platform": PLATFORM,
                    "registration_status": "registered",
                    "lifecycle_status": "active",
                    "data_classification": "public",
                    "internet_exposed": False,
                },
            )

            assert registration.status_code == 201, (
                f"Registration failed: HTTP {registration.status_code}"
            )

            application = registration.json()

            APP_ID = UUID(str(application["id"]))

            assert application["external_id"] == EXTERNAL_ID
            assert application["data_classification"] == "public"

            print("PASS: Disposable application created.")
            print("PASS: Authoritative classification is public.")

            print()
            print("===== CONTROLLED EGRESS WITH RESTRICTED DATA =====")

            with (
                patch.object(
                    main,
                    "verified_access_principal",
                    side_effect=verified_principal,
                ) as identity,
                patch.object(
                    main,
                    "authorize_and_persist",
                    side_effect=authorized_export,
                ) as access,
                patch.object(
                    main,
                    "check_jit_privilege",
                    side_effect=scoped_export_grant,
                ) as jit,
                patch.object(
                    main,
                    "evaluate_policy_and_persist",
                    side_effect=accepted_governance,
                ) as governance,
                patch.object(
                    integration.httpx,
                    "request",
                    side_effect=AssertionError(
                        "SECURITY FAILURE: outbound HTTP invoked"
                    ),
                ) as outbound,
            ):

                response = client.post(
                    f"/applications/{APP_ID}/controlled-egress",
                    headers={
                        "Authorization": TOKEN,
                    },
                    json={
                        "destination_url": (
                            "https://1.1.1.1/"
                            "lo4-egress-acceptance"
                        ),
                        "content": CONTENT,
                        "field_names": ["ssn"],
                        "method": "POST",
                    },
                )

                assert response.status_code == 200, (
                    "Controlled egress did not return "
                    f"the expected evaluation response: "
                    f"HTTP {response.status_code}"
                )

                result = response.json()

                identity.assert_called_once()
                access.assert_called_once()
                jit.assert_called_once()
                governance.assert_called_once()

                # Critical prevention assertion.
                outbound.assert_not_called()

            assert result["decision"] == "block"
            assert result["allowed"] is False
            assert result["executed"] is False
            assert result["upstream_status_code"] is None

            assert result["declared_classification"] == "public"
            assert result["effective_sensitivity"] == "restricted"

            assert (
                "restricted_data_external_transfer"
                in result["reasons"]
            )

            assert result["dlp"]["sensitive_data_detected"] is True
            assert result["dlp"]["finding_count"] >= 1
            assert (
                result["dlp"]["highest_sensitivity"]
                == "restricted"
            )

            assert CONTENT not in json.dumps(result)

            event_id = UUID(str(result["event_id"]))

            print("PASS: Identity, OPA and JIT fixtures invoked.")
            print("PASS: Real Gateway/DLP inspection completed.")
            print("PASS: Public classification escalated to restricted.")
            print("PASS: Transfer BLOCKED.")
            print("PASS: Zero outbound HTTP execution calls.")
            print("PASS: Raw synthetic content absent from response.")

        print()
        print("===== POSTGRESQL ENFORCEMENT RECEIPT =====")

        with get_connection() as connection:

            rows = connection.execute(
                """
                SELECT
                    id,
                    application_id,
                    declared_classification,
                    effective_sensitivity,
                    decision,
                    allowed,
                    reasons,
                    dlp_finding_count,
                    dlp_highest_sensitivity,
                    dlp_detected_types,
                    dlp_engine_version,
                    enforcement_outcome,
                    evaluated_at,
                    enforced_at,
                    upstream_status_code
                FROM integration_transfer_events
                WHERE application_id = %s
                """,
                (APP_ID,),
            ).fetchall()

        assert len(rows) == 1, (
            "Expected one isolated transfer audit record"
        )

        receipt = rows[0]

        assert receipt["id"] == event_id
        assert receipt["application_id"] == APP_ID

        assert receipt["declared_classification"] == "public"
        assert receipt["effective_sensitivity"] == "restricted"

        assert receipt["decision"] == "block"
        assert receipt["allowed"] is False

        assert receipt["dlp_finding_count"] >= 1
        assert receipt["dlp_highest_sensitivity"] == "restricted"
        assert receipt["dlp_engine_version"] == "dlp-v1"

        assert (
            "restricted_data_external_transfer"
            in receipt["reasons"]
        )

        assert receipt["enforcement_outcome"] == (
            "blocked_before_send"
        )

        assert receipt["evaluated_at"] is not None
        assert receipt["enforced_at"] is not None
        assert receipt["upstream_status_code"] is None

        assert CONTENT not in json.dumps(
            receipt, default=str
        )

        print("PASS: Exactly one matching audit event.")
        print("PASS: Restricted DLP metadata persisted.")
        print("PASS: BLOCK decision and reason persisted.")
        print("PASS: Enforcement = blocked_before_send.")
        print("PASS: Enforcement timestamp recorded.")
        print("PASS: No upstream HTTP status recorded.")
        print("PASS: Raw content absent from audit record.")

        print()
        print("PASS: LO4.3 deployed blocked-execution acceptance.")

    finally:
        print("\nHost runner handles scoped administrative cleanup.")


if __name__ == "__main__":
    run()

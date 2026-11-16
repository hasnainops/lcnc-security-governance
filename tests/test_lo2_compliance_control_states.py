
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app import dynamic_compliance


APP_ID = UUID("11111111-2222-3333-4444-555555555555")
DECIDED_AT = datetime(2026, 11, 11, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "changes,transfer,control_id,expected",
    [
        pytest.param(
            {},
            {"decision": "block"},
            "CTRL-05",
            "not_assessed",
            id="unknown-integrations-with-historical-transfer",
        ),
        pytest.param(
            {"external_integration_count": 0},
            None,
            "CTRL-05",
            "not_assessed",
            id="zero-integrations-incomplete-evidence",
        ),
        pytest.param(
            {
                "external_integration_count": 0,
                "unapproved_integration_count": 0,
                "connector_metadata": {},
            },
            None,
            "CTRL-05",
            "pass",
            id="zero-integrations-metadata-present",
        ),
        pytest.param(
            {"external_integration_count": 2},
            None,
            "CTRL-05",
            "not_assessed",
            id="external-integrations-no-dlp-event",
        ),
        pytest.param(
            {
                "governance_status": "pending_review",
                "governance_decided_at": DECIDED_AT,
            },
            None,
            "CTRL-07",
            "not_assessed",
            id="pending-review",
        ),
        pytest.param(
            {
                "governance_status": "unexpected_state",
                "governance_decided_at": DECIDED_AT,
            },
            None,
            "CTRL-07",
            "not_assessed",
            id="unknown-governance-state",
        ),
        pytest.param(
            {"governance_status": "completed"},
            None,
            "CTRL-07",
            "not_assessed",
            id="completed-without-decision-time",
        ),
        pytest.param(
            {
                "governance_status": "completed",
                "governance_decided_at": DECIDED_AT,
            },
            None,
            "CTRL-07",
            "pass",
            id="completed-with-decision-time",
        ),
        pytest.param(
            {
                "governance_status": "completed",
                "governance_decided_at": DECIDED_AT,
                "updated_at": datetime(
                    2026, 11, 11, 0, 1,
                    tzinfo=timezone.utc,
                ),
            },
            None,
            "CTRL-07",
            "pass",
            id="heartbeat-does-not-invalidate-governance",
        ),
        pytest.param(
            {
                "governance_status": "completed",
                "governance_decided_at": DECIDED_AT,
                "security_scanned_at": datetime(
                    2026, 11, 11, 0, 1,
                    tzinfo=timezone.utc,
                ),
            },
            None,
            "CTRL-07",
            "not_assessed",
            id="newer-security-scan-invalidates-governance",
        ),
        pytest.param(
            {
                "governance_status": "completed",
                "governance_decided_at": DECIDED_AT,
                "security_scan_status": "stale",
            },
            None,
            "CTRL-07",
            "not_assessed",
            id="stale-scan-invalidates-governance",
        ),
        pytest.param(
            {
                "governance_status": "blocked",
                "governance_decided_at": DECIDED_AT,
            },
            None,
            "CTRL-07",
            "fail",
            id="blocked-governance",
        ),
    ],
)
def test_compliance_control_states(
    monkeypatch, changes, transfer, control_id, expected
):
    application = {
        "name": "LO2 Test Application",
        "owner_name": None,
        "owner_email": None,
        "data_classification": "unknown",
        "external_integration_count": None,
        "unapproved_integration_count": None,
        "connector_metadata": None,
        "security_scan_status": "not_scanned",
        "security_scan_passed": None,
        "security_finding_count": None,
        "security_highest_severity": None,
        "governance_status": "not_evaluated",
        "governance_decided_at": None,
        "updated_at": DECIDED_AT,
    }
    application.update(changes)

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params):
            if "FROM applications" in query:
                self.row = application
            elif "FROM integration_transfer_events" in query:
                self.row = transfer
            elif "FROM access_decisions" in query:
                self.row = None
            else:
                raise AssertionError("Unexpected SQL query")
            return self

        def fetchone(self):
            return self.row

    monkeypatch.setattr(
        dynamic_compliance,
        "get_connection",
        FakeConnection,
    )

    result = dynamic_compliance.evaluate_dynamic_compliance(APP_ID)
    controls = {
        item["control_id"]: item
        for item in result["controls"]
    }

    assert len(controls) == 7
    assert controls[control_id]["status"] == expected

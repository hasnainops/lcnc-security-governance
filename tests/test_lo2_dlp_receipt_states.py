from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app import dynamic_compliance


APP_ID = UUID("11111111-2222-3333-4444-555555555555")


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("evaluation_only", "not_assessed"),
        ("fresh_block", "pass"),
        ("fresh_forward", "pass"),
        ("delivery_unconfirmed", "not_assessed"),
        ("stale_receipt", "not_assessed"),
        ("future_receipt", "not_assessed"),
        ("contradictory_decision", "not_assessed"),
        ("reversed_timestamps", "not_assessed"),
        ("missing_timestamp", "not_assessed"),
        ("naive_timestamp", "not_assessed"),
    ],
)
def test_dlp_enforcement_receipt_states(
    monkeypatch, scenario, expected
):
    monkeypatch.setenv(
        "DLP_RECEIPT_MAX_AGE_SECONDS", "86400"
    )

    now = datetime.now(timezone.utc)
    enforced_at = now - timedelta(minutes=1)

    transfer = {
        "enforcement_outcome": "blocked_before_send",
        "allowed": False,
        "decision": "block",
        "enforced_at": enforced_at,
        "evaluated_at": enforced_at - timedelta(seconds=1),
        "upstream_status_code": None,
    }

    if scenario == "evaluation_only":
        transfer["enforcement_outcome"] = None
        transfer["enforced_at"] = None

    elif scenario == "fresh_forward":
        transfer.update(
            enforcement_outcome="forwarded_upstream",
            allowed=True,
            decision="allow",
            upstream_status_code=202,
        )

    elif scenario == "delivery_unconfirmed":
        transfer.update(
            enforcement_outcome="delivery_unconfirmed",
            allowed=True,
            decision="allow",
        )

    elif scenario == "stale_receipt":
        transfer["enforced_at"] = now - timedelta(hours=25)
        transfer["evaluated_at"] = (
            transfer["enforced_at"] - timedelta(seconds=1)
        )

    elif scenario == "future_receipt":
        transfer["enforced_at"] = now + timedelta(hours=1)

    elif scenario == "contradictory_decision":
        transfer["allowed"] = True

    elif scenario == "reversed_timestamps":
        transfer["evaluated_at"] = enforced_at + timedelta(seconds=1)

    elif scenario == "missing_timestamp":
        transfer["enforced_at"] = None

    elif scenario == "naive_timestamp":
        transfer["enforced_at"] = enforced_at.replace(tzinfo=None)

    application = {
        "name": "LO2 DLP Receipt Test",
        "owner_name": None,
        "owner_email": None,
        "data_classification": "internal",
        "external_integration_count": 1,
        "unapproved_integration_count": 0,
        "connector_metadata": "{}",
        "security_scan_status": "not_scanned",
        "security_scan_passed": None,
        "security_finding_count": None,
        "security_highest_severity": None,
        "governance_status": "not_evaluated",
        "governance_decided_at": None,
    }

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
    assert controls["CTRL-05"]["status"] == expected

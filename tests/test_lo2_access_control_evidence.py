
from uuid import UUID

import pytest

from app import dynamic_compliance


APP_ID = UUID("11111111-2222-3333-4444-555555555555")


@pytest.mark.parametrize(
    "decision",
    [None, "allow", "deny"],
    ids=[
        "no-authorization-evidence",
        "recorded-allow",
        "recorded-deny",
    ],
)
def test_opa_decision_does_not_prove_enforcement(
    monkeypatch, decision
):
    application = {
        "name": "LO2 Access Control Test",
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
    }

    access_record = (
        None
        if decision is None
        else {
            "role": "developer",
            "requested_action": "export",
            "decision": decision,
        }
    )

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, _params):
            if "FROM applications" in query:
                self.row = application
            elif "FROM integration_transfer_events" in query:
                self.row = None
            elif "FROM access_decisions" in query:
                self.row = access_record
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

    result = dynamic_compliance.evaluate_dynamic_compliance(
        APP_ID
    )

    controls = {
        item["control_id"]: item
        for item in result["controls"]
    }

    assert len(controls) == 7
    assert controls["CTRL-06"]["status"] == "not_assessed"

    evidence = controls["CTRL-06"]["evidence"]

    if decision is None:
        assert "No OPA authorization evidence" in evidence
    else:
        assert f"decision={decision}" in evidence
        assert "not verified" in evidence

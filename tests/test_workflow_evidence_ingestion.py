import sys
from pathlib import Path
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE_API = ROOT / "governance-api"

sys.path.insert(
    0,
    str(GOVERNANCE_API),
)

from app import workflow_evidence


APPLICATION_ID = UUID(
    "11111111-2222-3333-4444-555555555555"
)


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.sql = None
        self.values = None

    def execute(self, sql, values):
        self.sql = sql
        self.values = values

        return FakeResult(
            {
                "id": APPLICATION_ID,
                "workflow_security_metadata": {
                    "page_count": 1,
                    "widget_count": 23,
                    "action_count": 9,
                    "api_action_count": 9,
                    "dynamic_binding_count": 8,
                    "invalid_action_count": 0,
                    "http_action_count": 7,
                    "https_action_count": 0,
                    "sensitive_header_action_count": 0,
                },
                "security_scan_status": "stale",
            }
        )

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False


def test_observed_workflow_evidence_is_persisted_and_scan_is_staled(
    monkeypatch,
):
    connection = FakeConnection()

    monkeypatch.setattr(
        workflow_evidence,
        "get_connection",
        lambda: connection,
    )

    metadata = (
        workflow_evidence
        .WorkflowSecurityMetadata(
            page_count=1,
            widget_count=23,
            action_count=9,
            api_action_count=9,
            dynamic_binding_count=8,
            invalid_action_count=0,
            http_action_count=7,
            https_action_count=0,
            sensitive_header_action_count=0,
        )
    )

    result = (
        workflow_evidence
        .persist_workflow_security_metadata(
            APPLICATION_ID,
            metadata,
        )
    )

    assert (
        "workflow_security_metadata"
        in connection.sql
    )

    assert (
        "IS DISTINCT FROM"
        in connection.sql
    )

    assert (
        "THEN 'stale'"
        in connection.sql
    )

    assert (
        "ELSE security_scan_status"
        in connection.sql
    )

    assert (
        result["workflow_security_metadata"]
        ["action_count"]
        == 9
    )

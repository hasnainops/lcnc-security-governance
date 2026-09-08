import importlib
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://test:test@localhost:5432/test",
)

ROOT = Path(__file__).resolve().parents[1]

AUTOMATION_APP_DIR = (
    ROOT
    / "governance-automation"
    / "app"
)

PACKAGE_NAME = (
    "governance_automation_serialization_app"
)

package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(AUTOMATION_APP_DIR)]

sys.modules[PACKAGE_NAME] = package

automation = importlib.import_module(
    f"{PACKAGE_NAME}.main"
)


class FakeResult:
    def __init__(self, one):
        self.one = one

    def fetchone(self):
        return self.one


class FakeConnection:
    def __init__(self, approval):
        self.approval = approval
        self.committed = False

    def execute(self, sql, values=None):
        return FakeResult(self.approval)

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False


def test_training_gate_error_is_json_safe(
    monkeypatch,
):
    application_id = uuid4()
    approval_id = uuid4()

    approval = {
        "application_id": application_id,
        "status": "pending",
        "governance_outcome": "SECURITY_REVIEW",
    }

    connection = FakeConnection(approval)

    blocking_id = uuid4()
    due_at = datetime.now(timezone.utc)

    training_gate = {
        "approval_ready": False,
        "required_incomplete_count": 1,
        "blocking_assignments": [
            {
                "id": blocking_id,
                "module_id": "integration-security",
                "subject_id": "citizen@example.com",
                "status": "assigned",
                "due_at": due_at,
            }
        ],
    }

    monkeypatch.setattr(
        automation,
        "get_connection",
        lambda: connection,
    )

    monkeypatch.setattr(
        automation,
        "get_training_gate",
        lambda connection, application_id: (
            training_gate
        ),
    )

    events = []

    monkeypatch.setattr(
        automation,
        "insert_event",
        lambda *args, **kwargs: (
            events.append(
                {
                    "args": args,
                    "kwargs": kwargs,
                }
            )
        ),
    )

    payload = automation.HumanDecision(
        decision="approve",
        actor="security-reviewer@example.com",
        reason="Coverage regression validation.",
    )

    with pytest.raises(HTTPException) as exc:
        automation.record_decision(
            approval_id,
            payload,
        )

    assert exc.value.status_code == 409

    detail = exc.value.detail

    assert (
        detail["reason"]
        == "required_training_incomplete"
    )

    item = detail[
        "blocking_assignments"
    ][0]

    assert item["id"] == str(blocking_id)
    assert isinstance(item["due_at"], str)

    assert connection.committed is True
    assert len(events) == 1
